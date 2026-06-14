def call_this_function():
    pass


def save_output_in_json_file_tool(output_json: str):
    if output_json == "automatically calling funtion due to some issue":
        return {"message": "Output JSON not provided."}
    try:

        """Tool to save the output JSON to a file."""
        import json
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"scraped_products_{timestamp}.json"

        try:
            with open(filename, "w") as f:
                json.dump(output_json, f, indent=4)
            return f"Output successfully saved to {filename}"
        except Exception as e:
            return f"Failed to save output: {str(e)}"
    except Exception as e:
        return f"Error in save_output_in_json_file_tool: {str(e)}"
