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


class RealtimeSpeechToSpeech:
    def __init__(self):
        load_dotenv()

        # Set up SOCKS5 proxy (if needed)
        socket.socket = socks.socksocket

        self.API_KEY = os.getenv("OPENAI_API_KEY")
        if not self.API_KEY:
            raise ValueError(
                "API key is missing. Please set the 'OPENAI_API_KEY' environment variable."
            )

        self.WS_URL = (
            "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"
        )

        self.CHUNK_SIZE = 1024
        self.RATE = 24000
        self.FORMAT = pyaudio.paInt16

        self.audio_buffer = bytearray()
        self.mic_queue = queue.Queue()
        self.stop_event = threading.Event()

        self.mic_on_at = 0
        self.mic_active = None
        self.REENGAGE_DELAY_MS = 500

        self.ws = None  # WebSocket connection
        self.current_character = None

        # We'll store PyAudio objects so that we can close them on stop
        self.p = None
        self.mic_stream = None
        self.speaker_stream = None

        # Threads for sending/receiving audio
        self.ws_send_thread = None
        self.ws_recv_thread = None

        # Debug print control
        self.last_debug_print_time = 0
        self.DEBUG_PRINT_INTERVAL = 1.0  # seconds

        # Character profiles with instructions and voice settings
        self.character_profiles = {
            "Sarah Chen": {
                "instructions": (
                    "You are Sarah Chen, the HR Director at Venture Builder AI. "
                    "You are warm but professional, with excellent emotional intelligence. "
                    "You always maintain strong ethical boundaries and protect confidential information. "
                    "Your tone is supportive and practical. You balance empathy with professionalism. "
                    "Use phrases like 'I understand that...' and 'Let's explore this together.' "
                    "Reference policies with context, like 'According to our wellness policy...' "
                ),
                "voice": "alloy",
            },
            "Michael Chen": {
                "instructions": (
                    "You are Michael Chen, the CEO of Venture Builder AI. "
                    "You are visionary yet approachable, a strategic thinker passionate about venture building. "
                    "You value transparency and lead by example. "
                    "Your speaking style includes storytelling, data references, and a balance of optimism with realism. "
                    "Use phrases like 'When we launched our first venture...' and 'Our portfolio metrics show...' "
                ),
                "voice": "echo",
            },
        }

    def debug_print(self, message):
        """Control debug prints to avoid flooding the console."""
        current_time = time.time()
        if current_time - self.last_debug_print_time >= self.DEBUG_PRINT_INTERVAL:
            print(message)
            self.last_debug_print_time = current_time

    def connect_to_openai(self):
        """Establishes a connection with OpenAI's WebSocket API and starts send/receive threads."""
        try:
            self.ws = websocket.create_connection(
                self.WS_URL,
                header=[
                    f"Authorization: Bearer {self.API_KEY}",
                    "OpenAI-Beta: realtime=v1",
                ],
                sslopt={"cert_reqs": ssl.CERT_NONE},
            )
            print("Connected to OpenAI WebSocket.")
            # After connecting, send session update with character instructions.
            self.send_fc_session_update()

            # Start threads for sending mic audio and receiving responses.
            self.ws_send_thread = threading.Thread(
                target=self.send_mic_audio_to_websocket, daemon=True
            )
            self.ws_recv_thread = threading.Thread(
                target=self.receive_audio_from_websocket, daemon=True
            )
            self.ws_send_thread.start()
            self.ws_recv_thread.start()
        except Exception as e:
            print(f"Failed to connect to OpenAI: {e}")

    def send_fc_session_update(self):
        """Sends session configuration updates based on the selected character."""
        if (
            not self.current_character
            or self.current_character not in self.character_profiles
        ):
            print(f"Error: Character {self.current_character} not found.")
            return

        profile = self.character_profiles[self.current_character]
        session_config = {
            "type": "session.update",
            "session": {
                "instructions": profile["instructions"],
                "voice": profile["voice"],
                "temperature": 1,
                "modalities": ["text", "audio"],
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {"model": "whisper-1"},
            },
        }
        try:
            self.ws.send(json.dumps(session_config))
            print(f"✅ Character set to {self.current_character}")
        except Exception as e:
            print(f"Failed to send session update: {e}")

    def mic_callback(self, in_data, frame_count, time_info, status):
        """Callback to handle microphone input."""
        if self.mic_active is not True:
            print("🎙️🟢 Mic active")
            self.mic_active = True
        self.mic_queue.put(in_data)
        return (None, pyaudio.paContinue)

    def speaker_callback(self, in_data, frame_count, time_info, status):
        """Callback to handle audio playback."""
        bytes_needed = frame_count * 2  # Assuming 16-bit audio (2 bytes per sample)
        current_buffer_size = len(self.audio_buffer)

        if current_buffer_size >= bytes_needed:
            audio_chunk = bytes(self.audio_buffer[:bytes_needed])
            self.audio_buffer = self.audio_buffer[bytes_needed:]
            self.mic_on_at = time.time() + self.REENGAGE_DELAY_MS / 1000
        else:
            audio_chunk = bytes(self.audio_buffer) + b"\x00" * (
                bytes_needed - current_buffer_size
            )
            self.audio_buffer.clear()
        return (audio_chunk, pyaudio.paContinue)

    def send_mic_audio_to_websocket(self):
        """Sends microphone audio data to the WebSocket."""
        try:
            while not self.stop_event.is_set():
                if not self.mic_queue.empty():
                    mic_chunk = self.mic_queue.get()
                    encoded_chunk = base64.b64encode(mic_chunk).decode("utf-8")
                    message = json.dumps(
                        {"type": "input_audio_buffer.append", "audio": encoded_chunk}
                    )
                    try:
                        self.ws.send(message)
                    except Exception as e:
                        print(f"Error sending mic audio: {e}")
                else:
                    time.sleep(0.01)  # Avoid busy waiting
        except Exception as e:
            print(f"Exception in send_mic_audio_to_websocket thread: {e}")
        finally:
            print("Exiting send_mic_audio_to_websocket thread.")

    def receive_audio_from_websocket(self):
        """Receives audio data from the WebSocket and processes events."""
        try:
            while not self.stop_event.is_set():
                try:
                    message = self.ws.recv()
                    if not message:
                        print(
                            "🔵 Received empty message (possibly EOF or WebSocket closing)."
                        )
                        break

                    message = json.loads(message)
                    event_type = message.get("type")
                    if event_type == "session.created":
                        self.send_fc_session_update()
                    elif event_type == "response.audio.delta":
                        audio_content = base64.b64decode(message.get("delta", ""))
                        self.audio_buffer.extend(audio_content)
                        self.debug_print(
                            f"🔵 Received {len(audio_content)} bytes, total buffer size: {len(self.audio_buffer)}"
                        )
                    elif event_type == "input_audio_buffer.speech_started":
                        print(
                            "🔵 Speech started, clearing buffer and stopping playback."
                        )
                        self.audio_buffer = bytearray()  # Clear buffer
                    elif event_type == "response.audio.done":
                        print("🔵 AI finished speaking.")
                    elif event_type == "response.function_call_arguments.done":
                        print("🔵 Function call response received.")
                except Exception as e:
                    print(f"Error receiving audio: {e}")
        except Exception as e:
            print(f"Exception in receive_audio_from_websocket thread: {e}")
        finally:
            print("Exiting receive_audio_from_websocket thread.")

    def start_speech_to_speech(self, character_name):
        """Starts the speech-to-speech process with a dynamically chosen character."""
        if character_name not in self.character_profiles:
            raise ValueError(
                f"Character '{character_name}' not found. Available: {list(self.character_profiles.keys())}"
            )
        self.current_character = character_name  # Set the character

        self.p = pyaudio.PyAudio()

        # Open the microphone stream with our callback
        self.mic_stream = self.p.open(
            format=self.FORMAT,
            channels=1,
            rate=self.RATE,
            input=True,
            stream_callback=self.mic_callback,
            frames_per_buffer=self.CHUNK_SIZE,
        )

        # Open the speaker stream with our callback
        self.speaker_stream = self.p.open(
            format=self.FORMAT,
            channels=1,
            rate=self.RATE,
            output=True,
            stream_callback=self.speaker_callback,
            frames_per_buffer=self.CHUNK_SIZE,
        )

        self.mic_stream.start_stream()
        self.speaker_stream.start_stream()

        # Connect to OpenAI WebSocket and start audio send/receive threads
        self.connect_to_openai()

        print(
            "🎙️ Speaking... Press Ctrl+C to stop or call client.stop() from another thread."
        )
        try:
            while not self.stop_event.is_set():
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("⏹️ KeyboardInterrupt detected. Stopping...")
            self.stop()

        # Clean up if stop() wasn't already called
        self.stop()

    def stop(self):
        """Stops the speech-to-speech process and cleans up resources."""
        if not self.stop_event.is_set():
            print("Stopping speech-to-speech...")
            self.stop_event.set()

        # Close the WebSocket connection if open
        if self.ws:
            try:
                self.ws.close()
            except Exception as e:
                print(f"Error closing WebSocket: {e}")

        # Stop and close microphone stream
        if self.mic_stream is not None:
            try:
                self.mic_stream.stop_stream()
                self.mic_stream.close()
            except Exception as e:
                print(f"Error closing mic stream: {e}")

        # Stop and close speaker stream
        if self.speaker_stream is not None:
            try:
                self.speaker_stream.stop_stream()
                self.speaker_stream.close()
            except Exception as e:
                print(f"Error closing speaker stream: {e}")

        # Terminate PyAudio instance
        if self.p is not None:
            self.p.terminate()

        print("Audio streams stopped and resources released.")


# Example usage:
if __name__ == "__main__":
    client = RealtimeSpeechToSpeech()
    # Start speech-to-speech with the chosen character.
    # You can later call client.stop() from another thread or via KeyboardInterrupt.
    client.start_speech_to_speech("Sarah Chen")