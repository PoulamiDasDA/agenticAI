# UTF-8 Encoding Fix for Azure Functions
import json
import logging

def safe_json_serialize(data):
    """
    Safely serialize data to JSON, handling UTF-8 encoding issues
    """
    try:
        # First attempt - normal serialization
        return json.dumps(data, ensure_ascii=False, indent=2)
    except (UnicodeDecodeError, UnicodeEncodeError) as e:
        logging.warning(f"UTF encoding issue detected: {e}")
        
        # Second attempt - clean the data
        cleaned_data = clean_utf8_data(data)
        return json.dumps(cleaned_data, ensure_ascii=True, indent=2)

def clean_utf8_data(obj):
    """
    Recursively clean UTF-8 encoding issues from nested objects
    """
    if isinstance(obj, dict):
        return {key: clean_utf8_data(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [clean_utf8_data(item) for item in obj]
    elif isinstance(obj, str):
        try:
            # Try to encode/decode to catch issues
            obj.encode('utf-8').decode('utf-8')
            return obj
        except (UnicodeDecodeError, UnicodeEncodeError):
            # Replace problematic characters
            return obj.encode('utf-8', errors='replace').decode('utf-8')
    else:
        return obj

def safe_return_result(result_dict):
    """
    Safely return result from activity function with UTF-8 handling
    """
    try:
        # Test if the result can be JSON serialized
        test_json = json.dumps(result_dict, ensure_ascii=False)
        return result_dict
    except (UnicodeDecodeError, UnicodeEncodeError, TypeError) as e:
        logging.error(f"Result serialization error: {e}")
        
        # Return a safe version
        return {
            'status': 'completed_with_encoding_issues',
            'original_error': str(e),
            'safe_result': clean_utf8_data(result_dict),
            'message': 'Result had UTF-8 encoding issues that were cleaned'
        }
