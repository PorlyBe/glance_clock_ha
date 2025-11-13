import logging

_LOGGER = logging.getLogger(__name__)


def hex_to_rgb(hex_color: int) -> tuple[int, int, int]:
    """Convert hex color to RGB tuple."""
    return (
        (hex_color >> 16) & 255,
        (hex_color >> 8) & 255,
        hex_color & 255
    )


def rgb_to_hex(r: int, g: int, b: int) -> int:
    """Convert RGB tuple to hex color."""
    return (r << 16) | (g << 8) | b


def parse_color_input(color_input, default_color):
    """Parse color input from service call, supporting both hex strings and integers."""
    if color_input is None:
        return default_color

    # If it's already an integer, return it
    if isinstance(color_input, int):
        return color_input

    # If it's a list (RGB array from color picker), convert to hex
    if isinstance(color_input, list) and len(color_input) >= 3:
        try:
            r, g, b = int(color_input[0]), int(
                color_input[1]), int(color_input[2])
            # Clamp values to 0-255
            r = max(0, min(255, r))
            g = max(0, min(255, g))
            b = max(0, min(255, b))
            return (r << 16) | (g << 8) | b
        except (ValueError, TypeError, IndexError):
            _LOGGER.warning(
                f"Invalid RGB array format: {color_input}, using default")
            return default_color

    # If it's a hex string (e.g., "#FF0000" or "FF0000")
    if isinstance(color_input, str):
        # Remove # if present
        hex_str = color_input.lstrip('#')
        try:
            return int(hex_str, 16)
        except ValueError:
            _LOGGER.warning(
                f"Invalid color format: {color_input}, using default")
            return default_color

    _LOGGER.warning(
        f"Unsupported color type: {type(color_input)}, using default")
    return default_color


def interpolate_color(value, min_val, max_val, min_color, max_color):
    """Interpolate color based on value between min_val and max_val."""
    if max_val == min_val:
        return min_color

    # Clamp value to range
    value = max(min_val, min(max_val, value))

    # Calculate interpolation factor (0.0 to 1.0)
    factor = (value - min_val) / (max_val - min_val)

    # Get RGB components
    min_r, min_g, min_b = hex_to_rgb(min_color)
    max_r, max_g, max_b = hex_to_rgb(max_color)

    # Interpolate each component
    r = int(min_r + (max_r - min_r) * factor)
    # Fixed: was using min_b instead of min_g
    g = int(min_g + (max_g - min_g) * factor)
    b = int(min_b + (max_b - min_b) * factor)

    return rgb_to_hex(r, g, b)
