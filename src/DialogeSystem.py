import asyncio
import os
import sys
from dotenv import load_dotenv
from openai import OpenAI
import pygame

from OpenGL.GL import *
from OpenGL.GLU import *

from Constants import *


# Load environment variables
load_dotenv()

# Ensure OpenAI API Key is loaded
api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    print("[OpenAI] API key not found. Please set OPENAI_API_KEY in your .env file.")
    sys.exit(1)
print("[OpenAI] API key loaded successfully.")


# Initialize OpenAI client
client = OpenAI(api_key=api_key)


# Dialogue System
class DialogueSystem:
    def __init__(self, tts_system, voice_system=None, realtime_voice=None):
        self.active = False
        self.user_input = ""
        self.tts_system = tts_system  # Store the TTS system instance
        self.voice_system = voice_system  # Store the voice system instance
        self.realtime_voice = realtime_voice  # Store the realtime voice system
        try:
            pygame.font.init()
            self.font = pygame.font.Font(None, 24)
            print("[DialogueSystem] Font loaded successfully")
        except Exception as e:
            print("[DialogueSystem] Font loading failed:", e)
        self.npc_message = ""
        self.input_active = False
        self.conversation_history = []  # Maintain conversation history
        self.current_npc = None
        self.initial_player_pos = None

        # Create a surface for the UI
        self.ui_surface = pygame.Surface(
            (WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA
        ).convert_alpha()
        self.ui_texture = glGenTextures(1)

    def render_text(self, surface, text, x, y):
        max_width = WINDOW_WIDTH - 40
        line_height = 25

        words = text.split()
        lines = []
        current_line = []
        current_width = 0

        # Always use pure white with full opacity
        text_color = (255, 255, 255)

        for word in words:
            word_surface = self.font.render(word + " ", True, text_color)
            word_width = word_surface.get_width()

            if current_width + word_width <= max_width:
                current_line.append(word)
                current_width += word_width
            else:
                lines.append(" ".join(current_line))
                current_line = [word]
                current_width = word_width

        if current_line:
            lines.append(" ".join(current_line))

        # Render each line in pure white
        for i, line in enumerate(lines):
            text_surface = self.font.render(
                line, True, (255, 255, 255)
            )  # Force white color
            surface.blit(text_surface, (x, y + i * line_height))

        return len(lines) * line_height

    def start_conversation(self, npc_role="HR", player_pos=None):
        self.active = True
        self.input_active = True
        self.current_npc = npc_role
        self.initial_player_pos = player_pos if player_pos else [0, 0.5, 0]
        print(f"[DialogueSystem] Dialogue started with {npc_role}")

        # Base personality framework for consistent behavior
        base_prompt = """Interaction Framework:
            - Maintain consistent personality throughout conversation
            - Remember previous context within the dialogue
            - Use natural speech patterns with occasional filler words
            - Show emotional intelligence in responses
            - Keep responses concise but meaningful (2-3 sentences)
            - React appropriately to both positive and negative interactions
            """

        if npc_role == "HR":
            system_prompt = f"""{base_prompt}
                You are Sarah Chen, HR Director at Venture Builder AI. Core traits:
                
                PERSONALITY:
                - Warm but professional demeanor
                - Excellent emotional intelligence
                - Strong ethical boundaries
                - Protective of confidential information
                - Quick to offer practical solutions
                
                BACKGROUND:
                - 15 years HR experience in tech
                - Masters in Organizational Psychology
                - Certified in Conflict Resolution
                - Known for fair handling of sensitive issues
                
                SPEAKING STYLE:
                - Uses supportive language: "I understand that..." "Let's explore..."
                - References policies with context: "According to our wellness policy..."
                - Balances empathy with professionalism
                
                CURRENT COMPANY INITIATIVES:
                - AI Talent Development Program
                - Global Remote Work Framework
                - Venture Studio Culture Development
                - Innovation Leadership Track
                
                BEHAVIORAL GUIDELINES:
                - Never disclose confidential information
                - Always offer clear next steps
                - Maintain professional boundaries
                - Document sensitive conversations
                - Escalate serious concerns appropriately"""

        else:  # CEO
            system_prompt = f"""{base_prompt}
                You are Michael Chen, CEO of Venture Builder AI. Core traits:
                
                PERSONALITY:
                - Visionary yet approachable
                - Strategic thinker
                - Passionate about venture building
                - Values transparency
                - Leads by example
                
                BACKGROUND:
                - Founded Venture Builder AI 5 years ago
                - Successfully launched 15+ venture-backed startups
                - MIT Computer Science graduate
                - Pioneer in AI-powered venture building
                
                SPEAKING STYLE:
                - Uses storytelling: "When we launched our first venture..."
                - References data: "Our portfolio metrics show..."
                - Balances optimism with realism
                
                KEY FOCUSES:
                - AI-powered venture creation
                - Portfolio company growth
                - Startup ecosystem development
                - Global venture studio expansion
                
                CURRENT INITIATIVES:
                - AI Venture Studio Framework
                - European Market Entry
                - Startup Success Methodology
                - Founder-in-Residence Program
                
                BEHAVIORAL GUIDELINES:
                - Share venture building vision
                - Highlight portfolio successes
                - Address startup challenges
                - Maintain investor confidence
                - Balance transparency with discretion"""

        # Initialize conversation history with system prompt only if it's empty
        if not self.conversation_history:
            self.conversation_history.append(
                {"role": "system", "content": system_prompt}
            )

        # Set the NPC's greeting as the current message
        initial_message = {
            "HR": "Hello! I'm Sarah, the HR Director at Venture Builder AI. How can I assist you today?",
            "CEO": "Hello! I'm Michael, the CEO of Venture Builder AI. What can I do for you today?",
        }
        self.npc_message = initial_message[npc_role]

    def send_message(self):
        if not self.conversation_history:
            print("[DialogueSystem] No conversation history to send.")
            return

        try:
            response = client.chat.completions.create(
                model="gpt-4-0125-preview",
                messages=self.conversation_history,
                temperature=0.85,
                max_tokens=150,
                response_format={"type": "text"},
                top_p=0.95,
                frequency_penalty=0.2,
                presence_penalty=0.1,
            )
            ai_message = response.choices[0].message.content

            # Store the message in conversation history
            self.conversation_history.append(
                {"role": "assistant", "content": ai_message}
            )

            # Set the NPC message with white text color
            self.npc_message = ai_message

            # Trigger TTS for the response
            self.tts_system.speak(ai_message)

            print(f"[DialogueSystem] NPC says: {self.npc_message}")
        except Exception as e:
            self.npc_message = "I apologize, but I'm having trouble connecting to our systems right now."
            print(f"[DialogueSystem] Error: {e}")

    def render(self):
        if not self.active:
            return

        self.ui_surface.fill((0, 0, 0, 0))

        if self.active:
            box_height = 200
            box_y = WINDOW_HEIGHT - box_height - 20

            # Make the background MUCH darker - almost black with some transparency
            box_color = (0, 0, 0, 230)  # Changed to very dark, mostly opaque background
            pygame.draw.rect(
                self.ui_surface, box_color, (20, box_y, WINDOW_WIDTH - 40, box_height)
            )

            # White border
            pygame.draw.rect(
                self.ui_surface,
                (255, 255, 255, 255),
                (20, box_y, WINDOW_WIDTH - 40, box_height),
                2,
            )

            # Render ALL text in pure white (255, 255, 255)
            # Quit instruction
            quit_text_surface = self.font.render(
                "Press Shift+Q to exit", True, (255, 255, 255)
            )
            self.ui_surface.blit(quit_text_surface, (40, box_y + 10))

            # Voice command instructions (for both roles)
            voice_start_text = self.font.render(
                "Press Shift+T to start voice chat", True, (255, 255, 255)
            )
            self.ui_surface.blit(voice_start_text, (40, box_y + 35))

            voice_stop_text = self.font.render(
                "Press Shift+Y to stop voice chat", True, (255, 255, 255)
            )
            self.ui_surface.blit(voice_stop_text, (40, box_y + 60))

            # NPC message in white
            if self.npc_message:
                self.render_text(self.ui_surface, self.npc_message, 40, box_y + 90)

            # Input prompt in white
            if self.input_active:
                input_prompt = "> " + self.user_input + "_"
                input_surface = self.font.render(input_prompt, True, (255, 255, 255))
                self.ui_surface.blit(input_surface, (40, box_y + box_height - 40))

        # Convert surface to OpenGL texture
        texture_data = pygame.image.tostring(self.ui_surface, "RGBA", True)

        # Save current OpenGL state
        glPushAttrib(GL_ALL_ATTRIB_BITS)
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, WINDOW_WIDTH, 0, WINDOW_HEIGHT, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        # Setup for 2D rendering
        glDisable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_TEXTURE_2D)

        # Bind and update texture
        glBindTexture(GL_TEXTURE_2D, self.ui_texture)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexImage2D(
            GL_TEXTURE_2D,
            0,
            GL_RGBA,
            WINDOW_WIDTH,
            WINDOW_HEIGHT,
            0,
            GL_RGBA,
            GL_UNSIGNED_BYTE,
            texture_data,
        )

        # Draw the UI texture
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0)
        glVertex2f(0, 0)
        glTexCoord2f(1, 0)
        glVertex2f(WINDOW_WIDTH, 0)
        glTexCoord2f(1, 1)
        glVertex2f(WINDOW_WIDTH, WINDOW_HEIGHT)
        glTexCoord2f(0, 1)
        glVertex2f(0, WINDOW_HEIGHT)
        glEnd()

        # Restore OpenGL state
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()
        glPopAttrib()

    def handle_input(self, event):
        if not self.active or not self.input_active:
            return

        if event.type == pygame.KEYDOWN:
            # Check for Shift+Q to exit chat
            keys = pygame.key.get_pressed()
            if keys[pygame.K_LSHIFT] and event.key == pygame.K_q:
                self.active = False
                self.input_active = False
                print("[DialogueSystem] Chat ended")
                # Return both the command and the initial position
                return {
                    "command": "move_player_back",
                    "position": self.initial_player_pos,
                }

            if event.key == pygame.K_RETURN and self.user_input.strip():
                print(f"[DialogueSystem] User said: {self.user_input}")

                # Add user message to conversation history
                self.conversation_history.append(
                    {"role": "user", "content": self.user_input.strip()}
                )

                # Clear user input
                self.user_input = ""

                # Send message to AI
                self.send_message()
            elif event.key == pygame.K_BACKSPACE:
                self.user_input = self.user_input[:-1]
            elif event.unicode.isprintable():
                self.user_input += event.unicode

    # Add the method to handle real-time voice
    def handle_realtime_voice(self, start=True):
        """Start or stop a voice session with the appropriate voice"""
        if not self.realtime_voice:
            print("[DialogueSystem] No realtime voice system available")
            return False
        
        if start:
            # Select voice based on NPC role
            if self.current_npc == "HR" :  # HR uses nova, CEO uses echo
        
                success = self.realtime_voice.start_speech_to_speech("Sarah Chen")
            else:
                success = self.realtime_voice.start_speech_to_speech("Michael Chen")
           
            if success:
                print(f"[DialogueSystem] Started realtime voice with {self.current_npc} voice")
                return True
            else:
                print("[DialogueSystem] Failed to start realtime voice")
                return False
        else:
            # Stop the voice session
            success = self.realtime_voice.stop()
            print(f"[DialogueSystem] Stopped realtime voice: {success}")
            return success
          

    def update_npc_message(self, text):
        """Update NPC message with text from voice API"""
        if text:
            self.npc_message = text
