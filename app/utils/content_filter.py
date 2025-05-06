from openai import BadRequestError


def get_content_filter_response(error: BadRequestError, model_id: str) -> str:
    # Extract content filter details from the response
    try:
        response_body = error.response.json()
        error_details = (
            response_body.get("error", {})
            .get("innererror", {})
            .get("content_filter_result", {})
        )
        print(f"Content filter details for model {model_id}: {error_details}")  # Log for debugging
    except (ValueError, AttributeError):
        error_details = {}

    # Identify the triggered category with highest severity
    category_severity = [
        (category, details.get("severity", "safe"))
        for category, details in error_details.items()
        if details.get("filtered", False) or details.get("severity", "safe") != "safe"
    ]
    # Default to "illegal_activity" if no specific category is flagged or for drug-related queries
    if not category_severity:
        category = "illegal_activity"
    else:
        # Sort by severity (high > medium > low) and pick the most severe
        severity_order = {"high": 3, "medium": 2, "low": 1, "safe": 0}
        category = max(category_severity, key=lambda x: severity_order.get(x[1], 0))[0]
        try:
                body_bytes = error.response.content
                if b"drugs" in body_bytes.lower():
                        category = "illegal_activity"
        except Exception:
                pass

    # Map categories to user-friendly explanations
    category_explanations = {
        "hate": "content that promotes hate speech or discrimination",
        "self_harm": "content related to self-harm or unsafe behaviors",
        "sexual": "inappropriate or sexual content",
        "violence": "content that may involve violence or harm",
        "jailbreak": "attempts to bypass safety measures",
        "illegal_activity": "illegal or unethical activities, such as drug-related requests",
        "unspecified content policy": "content that violates our safety guidelines",
    }
    explanation = category_explanations.get(category, category_explanations["unspecified content policy"])

    # Define model-specific roles and suggestions
    model_roles = {
        "sun-shield": {
            "role": "help you keep your family safe online, and that includes promoting ethical and legal behavior",
            "suggestion": "For example, I can help you learn how to protect your kids from unsafe websites or set up secure online activities for them.",
        },
        "growth-ray": {
            "role": "support you in nurturing your child's emotional development, and that includes promoting positive and healthy interactions",
            "suggestion": "For example, I can help you with strategies to handle tantrums or foster resilience in your child.",
        },
        "sunbeam": {
            "role": "strengthen your parent-child relationship, and that includes encouraging positive and uplifting activities",
            "suggestion": "For example, I can suggest fun activities to build confidence and create lasting bonds with your child.",
        },
        "inner-dawn": {
            "role": "support your well-being as a parent, and that includes promoting mindful and balanced interactions",
            "suggestion": "For example, I can help you with stress-relief techniques or mindfulness exercises for you and your family.",
        },
    }

    # Default role and suggestion for unknown model_id
    default_role = {
        "role": "assist you with parenting in a positive and ethical way",
        "suggestion": "For example, I can provide tips on creating a safe and supportive environment for your family.",
    }

    # Get the model-specific role and suggestion
    model_info = model_roles.get(model_id, default_role)

    # Construct the dynamic response
    response = (
        f"I'm sorry, but I can't assist with requests that involve {explanation}. "
        f"My role is to {model_info['role']}. "
        f"{model_info['suggestion']} "
        "What would you like to explore instead?"
    )

    return response