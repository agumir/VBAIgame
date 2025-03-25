import math
import time

import pygame
from OpenGL.GL import *
from OpenGL.GLU import *
from Constants import *
from DialogeSystem import DialogueSystem
from MenuScreen import MenuScreen
from NPC import NPC
from Player import Player
from World import World
from VoiceSystem import VoiceSystem
from TextToSpeechSystem import TextToSpeechSystem
from RealtimeVoiceSystem import RealtimeVoiceSystem
from RealtimeSpeechToSpeech import RealtimeSpeechToSpeech


class Game3D:
    def __init__(self):
        self.menu = MenuScreen()
        self.player = Player()
        self.world = World()
        self.voice_system = VoiceSystem()
        self.tts_system = TextToSpeechSystem(self.voice_system)
        self.realtime_voice = RealtimeSpeechToSpeech()
        self.dialogue = DialogueSystem(
            self.tts_system, self.voice_system, self.realtime_voice
        )
        self.hr_npc = NPC(-3.3, 0, -2, "HR")  # Moved beside the desk
        self.ceo_npc = NPC(3.3, 0, 1, "CEO")  # Moved beside the desk
        self.interaction_distance = 2.0
        self.last_interaction_time = 0
        self.recording_active = False

    def move_player_away_from_npc(self, npc_pos):
        # Calculate direction vector from NPC to player
        dx = self.player.pos[0] - npc_pos[0]
        dz = self.player.pos[2] - npc_pos[2]

        # Normalize the vector
        distance = math.sqrt(dx * dx + dz * dz)
        if distance > 0:
            dx /= distance
            dz /= distance

        # Move player back by 3 units
        self.player.pos[0] = npc_pos[0] + (dx * 3)
        self.player.pos[2] = npc_pos[2] + (dz * 3)

    def run(self):
        running = True
        while running:
            if self.menu.active:
                # Menu loop
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                    elif event.type == pygame.KEYDOWN:
                        if (
                            event.key == pygame.K_RETURN
                            and time.time() - self.menu.start_time
                            > (len(TITLE) / 15 + 1)
                        ):
                            self.menu.active = False
                            pygame.mouse.set_visible(False)
                            pygame.event.set_grab(True)
                        elif event.key == pygame.K_ESCAPE:
                            running = False

                self.menu.render()
            else:
                # Main game loop
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            pygame.mouse.set_visible(True)
                            pygame.event.set_grab(False)
                            running = False

                        # Handle dialogue key commands
                        keys = pygame.key.get_pressed()

                        # Shift+Q to exit dialogue
                        if keys[pygame.K_LSHIFT] and event.key == pygame.K_q:
                            if self.dialogue.active:
                                # If recording is active, stop it first
                                if self.recording_active:
                                    self.dialogue.handle_realtime_voice(start=False)
                                    self.recording_active = False

                                # Exit dialogue
                                self.dialogue.active = False
                                self.dialogue.input_active = False
                                print("[Game3D] Chat ended")
                                # Move player away from NPC
                                current_npc = (
                                    self.hr_npc
                                    if self.dialogue.current_npc == "HR"
                                    else self.ceo_npc
                                )
                                self.move_player_away_from_npc(current_npc.pos)

                        # Shift+T to start real-time voice
                        elif keys[pygame.K_LSHIFT] and event.key == pygame.K_t:
                            if self.dialogue.active and not self.recording_active:

                                success = self.dialogue.handle_realtime_voice(
                                    start=True
                                )
                                print(success)
                                if success:
                                    self.recording_active = True
                                    print("[Game3D] Real-time voice started")
                                else:
                                    print("[Game3D] Failed to start real-time voice")

                        # Shift+Y to stop real-time voice
                        elif keys[pygame.K_LSHIFT] and event.key == pygame.K_y:
                            if self.dialogue.active and self.recording_active:
                                success = self.dialogue.handle_realtime_voice(
                                    start=False
                                )
                                if success:
                                    self.recording_active = False
                                    print("[Game3D] Real-time voice stopped")
                                else:
                                    print("[Game3D] Failed to stop real-time voice")

                        # Other dialogue input handling
                        if self.dialogue.active:
                            result = self.dialogue.handle_input(event)
                            if (
                                isinstance(result, dict)
                                and result.get("command") == "move_player_back"
                            ):
                                # Move player away from NPC
                                current_npc = (
                                    self.hr_npc
                                    if self.dialogue.current_npc == "HR"
                                    else self.ceo_npc
                                )
                                self.move_player_away_from_npc(current_npc.pos)

                    elif event.type == pygame.MOUSEMOTION:
                        x, y = event.rel
                        self.player.update_rotation(x, y)

                # Handle keyboard input for movement (keep this blocked during dialogue)
                if not self.dialogue.active:
                    keys = pygame.key.get_pressed()
                    if keys[pygame.K_w]:
                        self.player.move(0, -1)
                    if keys[pygame.K_s]:
                        self.player.move(0, 1)
                    if keys[pygame.K_a]:
                        self.player.move(-1, 0)
                    if keys[pygame.K_d]:
                        self.player.move(1, 0)

                # Check NPC interactions
                current_time = time.time()
                if (
                    current_time - self.last_interaction_time > 0.5
                ):  # Cooldown on interactions
                    # Check distance to HR NPC
                    dx = self.player.pos[0] - self.hr_npc.pos[0]
                    dz = self.player.pos[2] - self.hr_npc.pos[2]
                    hr_distance = math.sqrt(dx * dx + dz * dz)

                    # Check distance to CEO NPC
                    dx = self.player.pos[0] - self.ceo_npc.pos[0]
                    dz = self.player.pos[2] - self.ceo_npc.pos[2]
                    ceo_distance = math.sqrt(dx * dx + dz * dz)

                    if (
                        hr_distance < self.interaction_distance
                        and not self.dialogue.active
                    ):
                        self.dialogue.start_conversation("HR", self.player.pos)
                        if self.dialogue.npc_message:
                            self.tts_system.speak(self.dialogue.npc_message)
                        self.last_interaction_time = current_time
                    elif (
                        ceo_distance < self.interaction_distance
                        and not self.dialogue.active
                    ):
                        self.dialogue.start_conversation("CEO", self.player.pos)
                        if self.dialogue.npc_message:
                            self.tts_system.speak(self.dialogue.npc_message)
                        self.last_interaction_time = current_time

                # Clear the screen and depth buffer
                glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

                # Save the current matrix
                glPushMatrix()

                # Apply player rotation and position
                glRotatef(self.player.rot[0], 1, 0, 0)
                glRotatef(self.player.rot[1], 0, 1, 0)
                glTranslatef(
                    -self.player.pos[0], -self.player.pos[1], -self.player.pos[2]
                )

                # Draw the world and NPCs
                self.world.draw()
                self.hr_npc.draw()
                self.ceo_npc.draw()

                # Restore the matrix
                glPopMatrix()

                # Render dialogue system (if active)
                self.dialogue.render()

                # Swap the buffers
                pygame.display.flip()

                # Maintain 60 FPS
                pygame.time.Clock().tick(60)

        pygame.quit()
