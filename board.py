def move_selected(tasks, selected):
    """Return the selected task in Done and preserve the other tasks."""
    return {key: ("done" if key == selected else current_state) for key, current_state in tasks.items()}
