import os
import threading
import time
import queue
from openai import OpenAI
import pygame
from dotenv import load_dotenv


class TextToSpeechSystem:
    def __init__(self, voice_system):
        self.voice_system = voice_system  # Store the VoiceSystem instance
        load_dotenv()

        # Initialize OpenAI client
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "API key is missing. Please set the 'OPENAI_API_KEY' environment variable."
            )

        self.client = OpenAI(api_key=self.api_key)

        # Initialize pygame mixer for audio playback
        pygame.mixer.init(frequency=24000)

        # Queue for text messages to be processed
        self.text_queue = queue.Queue()

        # Control flags
        self.stop_event = threading.Event()
        self.is_processing = False

        # Start processing thread
        self.processing_thread = threading.Thread(target=self._process_text_queue)
        self.processing_thread.daemon = True
        self.processing_thread.start()

        print("[TextToSpeechSystem] Initialized with VoiceSystem")

    def _process_text_queue(self):
        while not self.stop_event.is_set():
            try:
                if not self.text_queue.empty():
                    text = self.text_queue.get()
                    self.is_processing = True

                    # Generate speech using OpenAI API
                    try:
                        response = self.client.audio.speech.create(
                            model="tts-1", voice="alloy", input=text
                        )

                        # Save the audio to a temporary file
                        temp_file = "temp_speech.mp3"
                        response.stream_to_file(temp_file)

                        # Play the audio
                        pygame.mixer.music.load(temp_file)
                        pygame.mixer.music.play()

                        # Wait for the audio to finish playing
                        while pygame.mixer.music.get_busy():
                            time.sleep(0.1)
                            if self.stop_event.is_set():
                                break

                        # Clean up
                        pygame.mixer.music.unload()
                        if os.path.exists(temp_file):
                            os.remove(temp_file)

                    except Exception as e:
                        print(f"[TextToSpeechSystem] Error generating speech: {e}")

                    self.is_processing = False
                    self.text_queue.task_done()
                else:
                    time.sleep(0.1)
            except Exception as e:
                print(f"[TextToSpeechSystem] Error in processing thread: {e}")
                time.sleep(0.1)

    def speak(self, text):
        """Add text to the queue to be spoken"""
        if text:
            self.text_queue.put(text)
            return True
        return False

    def stop(self):
        """Stop the text-to-speech system"""
        self.stop_event.set()

        # Stop any playing audio
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()

        # Wait for processing thread to finish
        if self.processing_thread.is_alive():
            self.processing_thread.join(timeout=2)

        print("[TextToSpeechSystem] Stopped")