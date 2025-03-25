# 3D Adventure Game Engine
import os
import pygame
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *
import Game3D

def initialize_pygame():
    """Configure Pygame with OpenGL settings"""
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "hide"
    pygame.init()
    return (800, 600)  # Default display dimensions

def setup_opengl_context(display_size):
    """Initialize OpenGL context with version and buffer settings"""
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 2)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 1)
    return pygame.display.set_mode(display_size, DOUBLEBUF | OPENGL)

def configure_3d_view(display_size):
    """Set up 3D projection and camera parameters"""
    glEnable(GL_DEPTH_TEST)
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(45, (display_size[0] / display_size[1]), 0.1, 50.0)
    glMatrixMode(GL_MODELVIEW)
    glTranslatef(0.0, 0.0, -5)  # Initial camera position

def setup_lighting():
    """Configure basic scene lighting"""
    glEnable(GL_LIGHTING)
    glEnable(GL_LIGHT0)
    glLightfv(GL_LIGHT0, GL_POSITION, [0, 5, 5, 1])
    glLightfv(GL_LIGHT0, GL_AMBIENT, [0.5, 0.5, 0.5, 1])
    glLightfv(GL_LIGHT0, GL_DIFFUSE, [1.0, 1.0, 1.0, 1])

def enable_transparency():
    """Enable alpha blending for transparent objects"""
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

def main():
    """Main game initialization and execution"""
    display_size = initialize_pygame()
    screen = setup_opengl_context(display_size)
    configure_3d_view(display_size)
    setup_lighting()
    enable_transparency()
    
    # Initialize and run the game
    adventure_game = Game3D.Game3D()
    adventure_game.run()

if __name__ == "__main__":
    main()