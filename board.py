def move_selected(tasks, selected):
    """Return the selected task in Done and preserve the other tasks."""
    selected_ids = selected if isinstance(selected, list) else [selected]
    return {key: ("done" if key in selected_ids else state) for key, state in tasks.items()}
