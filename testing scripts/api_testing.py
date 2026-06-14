import os
import google.genai as genai

# Set up the API key
# Replace 'YOUR_API_KEY' with your actual Google AI API key
# Or set it as an environment variable: export GOOGLE_API_KEY=your_key_here
api_key = "AIzaSyB_WmqEZ24YDZvHNL59TXA-kN32xS-oIyg"
if not api_key:
    raise ValueError(
        "Please set the GOOGLE_API_KEY environment variable or replace 'YOUR_API_KEY' with your actual API key."
    )

client = genai.Client(api_key=api_key)

# List all available models
models = client.models.list()
print("Available models:")
for model in models:
    print(f"- {model.name}")

# Choose a model (e.g., gemini-1.5-flash if available, or pick from the list)
chosen_model = (
    "gemini-2.5-flash-lite"  # Change this to any available model from the list above
)

# Send the message
response = client.models.generate_content(
    model=chosen_model, contents="Hello how are you"
)

# Print the response
print(f"\nResponse from {chosen_model}:")
print(response.text)
