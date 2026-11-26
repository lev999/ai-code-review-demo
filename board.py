def move_selected(tasks, selected):
    """Return the selected task in Done and preserve the other tasks."""
    return {key: ("done" if key == selected else state) for key, state in tasks.items()}
