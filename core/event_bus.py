class EventBus:
    def __init__(self):
        self.listeners = {}

    def on(self, event_name, handler):
        if event_name not in self.listeners:
            self.listeners[event_name] = []
        self.listeners[event_name].append(handler)

    def emit(self, event_name, data=None):
        if event_name in self.listeners:
            for handler in self.listeners[event_name]:
                try:
                    handler(data)
                except Exception as e:
                    print(f"EventBus error in handler for '{event_name}': {e}")
                    if event_name != "error":
                        self.emit("error", f"Error in {event_name}: {str(e)}")
