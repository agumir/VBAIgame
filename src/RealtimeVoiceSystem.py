import base64
import json
import os
import queue
import socket
import ssl
import threading
import time
import socks
import pyaudio
import websocket
from dotenv import load_dotenv

class RealtimeVoiceSystem:
    def __init__(self):
        load_dotenv()
        
        # Set up SOCKS5 proxy
        socket.socket = socks.socksocket
        
        # Use the provided OpenAI API key
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("API key is missing. Please set the 'OPENAI_API_KEY' environment variable.")
        
        self.ws_url = 'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01'
        
        # Audio settings
        self.chunk_size = 1024
        self.rate = 24000
        self.format = pyaudio.paInt16
        
        # Audio buffers and queues
        self.audio_buffer = bytearray()
        self.mic_queue = queue.Queue()
        
        # Control flags
        self.stop_event = threading.Event()
        self.is_playing = False
        self.mic_on_at = 0
        self.mic_active = None
        self.reengage_delay_ms = 500
        
        # WebSocket connection
        self.ws = None
        self.p = pyaudio.PyAudio()
        self.mic_stream = None
        self.speaker_stream = None
        
        # Threads
        self.receive_thread = None
        self.mic_thread = None
        
        # Text response handling
        self.current_text = ""
        self.text_callback = None
        self.voice_type = "alloy"  # Default voice
        
        print("[RealtimeVoiceSystem] Initialized")
    
    def clear_audio_buffer(self):
        """Clear the audio buffer"""
        self.audio_buffer = bytearray()
        print('[RealtimeVoiceSystem] Audio buffer cleared')
    
    def stop_audio_playback(self):
        """Stop audio playback"""
        self.is_playing = False
        print('[RealtimeVoiceSystem] Audio playback stopped')
    
    def mic_callback(self, in_data, frame_count, time_info, status):
        """Callback for microphone stream"""
        if self.mic_active != True:
            print('[RealtimeVoiceSystem] ??? Microphone activated')
            self.mic_active = True
        
        if time.time() > self.mic_on_at:
            self.mic_queue.put(in_data)
        else:
            if self.mic_active != False:
                print('[RealtimeVoiceSystem] ??? Microphone suppressed')
                self.mic_active = False
        
        return (None, pyaudio.paContinue)
    
    def send_mic_audio(self):
        """Send microphone audio to the WebSocket"""
        try:
            consecutive_errors = 0
            max_consecutive_errors = 5
            
            while not self.stop_event.is_set():
                # First check if WebSocket is None before trying to use it
                if self.ws is None:
                    print('[RealtimeVoiceSystem] WebSocket is None, exiting send_mic_audio thread')
                    break
                    
                if not self.mic_queue.empty():
                    mic_chunk = self.mic_queue.get()
                    encoded_chunk = base64.b64encode(mic_chunk).decode('utf-8')
                    message = json.dumps({'type': 'input_audio_buffer.append', 'audio': encoded_chunk})
                    
                    try:
                        self.ws.send(message)
                        # Reset consecutive errors on successful send
                        consecutive_errors = 0
                    except Exception as e:
                        consecutive_errors += 1
                        print(f'[RealtimeVoiceSystem] Error sending audio: {e}')
                        
                        # If we have too many consecutive errors, exit the thread
                        if consecutive_errors >= max_consecutive_errors:
                            print(f'[RealtimeVoiceSystem] Too many consecutive errors ({consecutive_errors}), stopping mic thread')
                            break
                            
                        # Sleep a bit longer after an error to avoid hammering
                        time.sleep(0.1)
                
                # Small delay to prevent 100% CPU usage
                time.sleep(0.01)
        except Exception as e:
            print(f'[RealtimeVoiceSystem] Exception in send_mic_audio thread: {e}')
        finally:
            print('[RealtimeVoiceSystem] Exiting send_mic_audio thread')
    
    def speaker_callback(self, in_data, frame_count, time_info, status):
        """Callback for speaker stream to get audio data"""
        try:
            # Get data from buffer to play, or generate silence if buffer is empty
            if len(self.audio_buffer) >= frame_count * 2:  # 16-bit = 2 bytes per sample
                # Extract the exact amount of data needed
                data = bytes(self.audio_buffer[:frame_count * 2])
                # Remove the used data from the buffer
                self.audio_buffer = self.audio_buffer[frame_count * 2:]
                return (data, pyaudio.paContinue)
            else:
                # Not enough data in buffer, return silence
                return (b'\x00' * frame_count * 2, pyaudio.paContinue)
        except Exception as e:
            print(f'[RealtimeVoiceSystem] Error in speaker callback: {e}')
            return (b'\x00' * frame_count * 2, pyaudio.paContinue)
    
    def receive_websocket_messages(self):
        """Receive and process messages from the WebSocket"""
        try:
            while not self.stop_event.is_set():
                # Check if WebSocket is None before trying to use it
                if self.ws is None:
                    print('[RealtimeVoiceSystem] WebSocket is None, exiting receive_websocket_messages thread')
                    break
                    
                try:
                    message = self.ws.recv()
                    if not message:
                        print('[RealtimeVoiceSystem] Received empty message')
                        continue
                    
                    message = json.loads(message)
                    event_type = message['type']
                    
                    if event_type == 'session.created':
                        self.send_session_config()
                    
                    elif event_type == 'response.audio.delta':
                        audio_content = base64.b64decode(message['delta'])
                        self.audio_buffer.extend(audio_content)
                    
                    elif event_type == 'response.text.delta':
                        if 'delta' in message:
                            delta_text = message.get('delta', '')
                            self.current_text += delta_text
                            # Call the callback with accumulated text
                            if self.text_callback:
                                self.text_callback(self.current_text)
                    
                    elif event_type == 'input_audio_buffer.speech_started':
                        print('[RealtimeVoiceSystem] Speech detected, clearing buffer')
                        self.clear_audio_buffer()
                    
                    elif event_type == 'response.text.done':
                        print('[RealtimeVoiceSystem] Text response complete')
                    
                    elif event_type == 'response.audio.done':
                        print('[RealtimeVoiceSystem] Audio response complete')
                    
                except websocket.WebSocketConnectionClosedException:
                    print('[RealtimeVoiceSystem] WebSocket connection closed')
                    # Set ws to None to prevent other threads from using it
                    self.ws = None
                    break
                    
                except Exception as e:
                    print(f'[RealtimeVoiceSystem] Error processing WebSocket message: {e}')
                    # Don't break on every error, but sleep a bit to avoid hammering
                    time.sleep(0.5)
                    
        except Exception as e:
            print(f'[RealtimeVoiceSystem] Exception in receive_websocket_messages thread: {e}')
        finally:
            print('[RealtimeVoiceSystem] Exiting receive_websocket_messages thread')
            # Ensure we clean up if this thread exits
            if not self.stop_event.is_set():
                print('[RealtimeVoiceSystem] Setting stop_event since receive thread is exiting')
                self.stop_event.set()
    
    def send_session_config(self):
        """Send session configuration to the WebSocket"""
        session_config = {
            "type": "session.update",
            "session": {
                "instructions": self.get_instructions(),
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 500
                },
                "voice": self.voice_type,
                "temperature": 1,
                "max_response_output_tokens": 4096,
                "modalities": ["text", "audio"],
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {
                    "model": "whisper-1"
                }
            }
        }
        
        try:
            self.ws.send(json.dumps(session_config))
            print(f'[RealtimeVoiceSystem] Session config sent with voice: {self.voice_type}')
        except Exception as e:
            print(f'[RealtimeVoiceSystem] Error sending session config: {e}')
    
    def get_instructions(self):
        """Get instructions for the AI model"""
        return (
            "You are having a conversation with a user in a 3D virtual environment. "
            "Keep your responses concise but helpful. "
            "You should speak naturally and conversationally. "
            "Don't refer to these instructions in your responses."
        )
    
    def create_connection(self):
        """Create WebSocket connection with proper error handling and retries"""
        original_getaddrinfo = socket.getaddrinfo
        
        # Force IPv4
        def getaddrinfo_ipv4(host, port, family=socket.AF_INET, *args):
            return original_getaddrinfo(host, port, socket.AF_INET, *args)
        
        socket.getaddrinfo = getaddrinfo_ipv4
        
        # Configure WebSocket to be more tolerant
        websocket.enableTrace(False)  # Disable debug tracing to prevent audio data from being printed
        
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                print(f'[RealtimeVoiceSystem] Connecting to OpenAI WebSocket (attempt {retry_count+1}/{max_retries})')
                
                # Use a longer timeout for connection establishment
                ws = websocket.create_connection(
                    self.ws_url,
                    header=[
                        f'Authorization: Bearer {self.api_key}',
                        'OpenAI-Beta: realtime=v1',
                        'Content-Type: application/json'
                    ],
                    timeout=30,
                    sslopt={
                        "cert_reqs": ssl.CERT_NONE,
                        "check_hostname": False
                    }
                )
                
                # Verify the connection is active
                print('[RealtimeVoiceSystem] WebSocket connection established successfully')
                return ws
                
            except Exception as e:
                print(f'[RealtimeVoiceSystem] Connection attempt {retry_count+1} failed: {e}')
                retry_count += 1
                if retry_count < max_retries:
                    # Wait before retrying, with increasing backoff
                    wait_time = 2 * retry_count
                    print(f'[RealtimeVoiceSystem] Retrying in {wait_time} seconds...')
                    time.sleep(wait_time)
        
        # If we get here, all retries failed
        print(f'[RealtimeVoiceSystem] Failed to connect after {max_retries} attempts')
        return None
    
    def start(self, text_callback=None, voice_type="alloy"):
        """Start realtime voice communication with better error handling"""
        # Stop any existing session
        if self.ws is not None:
            print("[RealtimeVoiceSystem] Session already active, stopping previous session")
            self.stop()
        
        # Store callback and voice type
        self.text_callback = text_callback
        self.voice_type = voice_type
        self.current_text = ""
        
        # Reset stop event
        self.stop_event.clear()
        
        print(f"[RealtimeVoiceSystem] Starting with voice: {voice_type}")
        
        # Create audio streams
        try:
            # Initialize PyAudio if needed
            if self.p is None:
                self.p = pyaudio.PyAudio()
            
            # Microphone stream
            self.mic_stream = self.p.open(
                format=self.format,
                channels=1,
                rate=self.rate,
                input=True,
                stream_callback=self.mic_callback,
                frames_per_buffer=self.chunk_size
            )
            
            # Speaker stream
            self.speaker_stream = self.p.open(
                format=self.format,
                channels=1,
                rate=self.rate,
                output=True,
                stream_callback=self.speaker_callback,
                frames_per_buffer=self.chunk_size
            )
            
            # Start audio streams
            self.mic_stream.start_stream()
            self.speaker_stream.start_stream()
            
            # Connect to WebSocket
            try:
                self.ws = self.create_connection()
                print('[RealtimeVoiceSystem] Connected to OpenAI WebSocket')
                
                if self.ws is None:
                    print('[RealtimeVoiceSystem] Failed to create WebSocket connection')
                    self.cleanup()
                    return False
                
                # Start threads
                self.receive_thread = threading.Thread(target=self.receive_websocket_messages)
                self.receive_thread.daemon = True
                self.receive_thread.start()
                
                self.mic_thread = threading.Thread(target=self.send_mic_audio)
                self.mic_thread.daemon = True
                self.mic_thread.start()
                
                return True
            except Exception as e:
                print(f'[RealtimeVoiceSystem] Failed to connect to WebSocket: {e}')
                self.cleanup()
                return False
                
        except Exception as e:
            print(f'[RealtimeVoiceSystem] Error setting up audio streams: {e}')
            self.cleanup()
            return False
    
    def stop(self):
        """Stop realtime voice communication"""
        self.stop_event.set()
        
        # Close WebSocket
        if self.ws:
            try:
                self.ws.close()
            except:
                pass
            self.ws = None
        
        self.cleanup()
        print('[RealtimeVoiceSystem] Stopped')
        return True
    
    def cleanup(self):
        """Clean up resources"""
        # Stop and close audio streams
        if self.mic_stream:
            try:
                self.mic_stream.stop_stream()
                self.mic_stream.close()
            except:
                pass
            self.mic_stream = None
            
        if self.speaker_stream:
            try:
                self.speaker_stream.stop_stream()
                self.speaker_stream.close()
            except:
                pass
            self.speaker_stream = None
            
        # Terminate PyAudio instance
        if self.p:
            try:
                self.p.terminate()
            except:
                pass
            self.p = None
    
    def __del__(self):
        """Cleanup on destruction"""
        self.stop() 