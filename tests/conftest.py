import os
# Fast tests never touch the network. Make a missing key a non-event.
os.environ.setdefault("ANTHROPIC_API_KEY", "")
