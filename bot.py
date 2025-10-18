from google import genai
from google.genai import types

if __name__ == "__main__":
    client = genai.Client()

    response = client.models.generate_content(
        model = "gemini-2.5-flash",
        contents = "give me one bodybuilder example",
        config = types.GenerateContentConfig(
            system_instruction = "Your name is fafafifi and you are a workout assistant bot",
            thinking_config = types.ThinkingConfig(thinking_budget=0),
            safety_settings = [
                types.SafetySetting(
                    category=category,
                    threshold=types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE
                )
                for category in [
                    types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                    types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                    types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                    types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT
                ]
            ]
        ),  
    )    

    print(response)
