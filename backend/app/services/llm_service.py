from openai import Completion
from app.core.config import Settings
from app.schema.tweet import Tweet

settings = Settings()

# HUMAN ASSISTANCE NEEDED
# The following function needs review and potential modifications for production readiness.
# The confidence level is low (0.5), indicating that the implementation might not be optimal.
def generate_response(tweet: Tweet) -> str:
    # Prepare the prompt using tweet content and context
    prompt = f"Generate a response to the following tweet: '{tweet.content}'\n"
    prompt += f"Context: The tweet was posted by {tweet.author} on {tweet.created_at}\n"
    prompt += "Response:"

    # Call the OpenAI API to generate a response
    try:
        response = Completion.create(
            engine=settings.openai_engine,
            prompt=prompt,
            max_tokens=150,
            n=1,
            stop=None,
            temperature=0.7,
        )
    except Exception as e:
        # TODO: Implement proper error handling and logging
        print(f"Error calling OpenAI API: {str(e)}")
        return "Sorry, I couldn't generate a response at this time."

    # Process and format the generated response
    generated_text = response.choices[0].text.strip()

    # TODO: Implement additional processing or formatting if needed

    # Return the formatted response
    return generated_text