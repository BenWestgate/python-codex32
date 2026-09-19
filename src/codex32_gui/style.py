"""The whole stylesheet.

Only libadwaita's named colours are used, so dark mode and the operator's accent
colour work without a second stylesheet, and only the system monospace font is
named, so no font file is shipped or downloaded.
"""

CSS = """
.card-entry {
  font-family: monospace;
  font-size: 1.1rem;
  letter-spacing: 0.06em;
}
.card-group {
  font-family: monospace;
  font-size: 1.35rem;
  font-weight: bold;
  padding: 4px 9px;
  border-radius: 6px;
  background-color: alpha(currentColor, 0.09);
}
.card-group.guessed {
  background-color: alpha(@warning_color, 0.35);
}
.card-frame {
  border: 2px solid @error_color;
  border-radius: 12px;
  padding: 14px;
}
.reading {
  font-size: 0.9rem;
}
.reading.error {
  color: @error_color;
}
.reading.warning {
  color: @warning_color;
}
.reading.success {
  color: @success_color;
}
"""
