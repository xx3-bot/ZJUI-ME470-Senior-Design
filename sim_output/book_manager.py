"""Book position manager for sim_output."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BookPosition:
    """Current position of the return book."""

    x: float  # mm, left/right from arm base
    y: float  # mm, forward from arm base
    z: float = 100.0  # mm, book-spine grasp height above base

    def as_tuple(self) -> tuple[float, float, float]:
        """Return position as (x, y, z) tuple."""
        return (self.x, self.y, self.z)


class BookManager:
    """Manages the position of the return book in sim_output.

    The XY coordinate system is defined with the arm base yaw joint as the origin.
    X is left/right from the arm base, Y is forward from the arm base.
    """

    # Default position: side return bin around 90 degrees from forward
    DEFAULT_X = 280.0
    DEFAULT_Y = 100.0
    DEFAULT_Z = 100.0

    # Valid range for book position (mm)
    VALID_X_RANGE = (-200.0, 400.0)
    VALID_Y_RANGE = (50.0, 350.0)
    VALID_Z_RANGE = (20.0, 200.0)

    def __init__(
        self,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
    ) -> None:
        """Initialize book manager with optional custom position."""
        self.position = BookPosition(
            x=x if x is not None else self.DEFAULT_X,
            y=y if y is not None else self.DEFAULT_Y,
            z=z if z is not None else self.DEFAULT_Z,
        )
        self._validate_position(self.position)

    def set_position(self, x: float, y: float, z: float | None = None) -> bool:
        """
        Set the book position.
        
        Returns:
            True if position is valid and updated, False otherwise.
        """
        new_z = z if z is not None else self.position.z
        new_position = BookPosition(x, y, new_z)
        
        if not self._validate_position(new_position):
            return False
        
        self.position = new_position
        return True

    def get_position(self) -> BookPosition:
        """Get the current book position."""
        return self.position

    def get_position_tuple(self) -> tuple[float, float, float]:
        """Get the current book position as (x, y, z) tuple."""
        return self.position.as_tuple()

    def is_position_valid(self, x: float, y: float, z: float | None = None) -> bool:
        """Check if a position is within valid range."""
        test_z = z if z is not None else self.DEFAULT_Z
        return (
            self.VALID_X_RANGE[0] <= x <= self.VALID_X_RANGE[1]
            and self.VALID_Y_RANGE[0] <= y <= self.VALID_Y_RANGE[1]
            and self.VALID_Z_RANGE[0] <= test_z <= self.VALID_Z_RANGE[1]
        )

    def _validate_position(self, position: BookPosition) -> bool:
        """Validate a position and raise error if invalid."""
        if not self.is_position_valid(position.x, position.y, position.z):
            raise ValueError(
                f"Book position ({position.x}, {position.y}, {position.z}) "
                f"out of valid range: "
                f"x∈[{self.VALID_X_RANGE[0]}, {self.VALID_X_RANGE[1]}], "
                f"y∈[{self.VALID_Y_RANGE[0]}, {self.VALID_Y_RANGE[1]}], "
                f"z∈[{self.VALID_Z_RANGE[0]}, {self.VALID_Z_RANGE[1]}]"
            )
        return True
