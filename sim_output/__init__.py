"""
sim_output: Simulation backend for book-reshelving control system.

This module provides:
1. Motion simulation (move_to, gripper_command)
2. Reachability checking via IK helper
3. Book position management
4. Structured logging of all operations

Usage:
    When SIM_MODE=True in config, motion_adapter calls this backend instead of real hardware.
"""

__version__ = "0.1.0"
