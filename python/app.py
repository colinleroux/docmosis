from flask import (
    Flask,
    render_template,
    request,
    flash,
    send_from_directory,
    url_for,
    session,
)
import os
import requests
import io
import csv
import json
import git

# Initialize Flask app
app = Flask(__name__)
app.secret_key = "thisismysupersecretkey"  # Use a secure key in production

# Output directory for generated files
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "generated_files")
os.makedirs(OUTPUT_DIR, exist_ok=True)  # Ensure the directory exists


@app.route("/", methods=["GET", "POST"])
def docmosis_form():
    """
    Handles the main form for uploading CSVs, previewing JSON data,
    and submitting data to the Docmosis API.
    """
    json_data = session.pop("json_data", "")  # Load saved JSON from session if available

    if request.method == "POST":
        action = request.form.get("action")

        if action == "upload":  # Handle CSV Upload
            file = request.files.get("file")
            if not file or file.filename == "":
                flash("No file selected. Please choose a CSV file.", "danger")
            else:
                try:
                    # Read and process CSV
                    stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
                    reader = csv.DictReader(stream)

                    # Validate required headers
                    required_headers = {"qty", "ItemName", "itemDescription", "amt"}
                    if not required_headers.issubset(reader.fieldnames):
                        raise ValueError(
                            "CSV file must contain the following headers: 'qty', 'ItemName', 'itemDescription', 'amt'"
                        )

                    # Convert rows to JSON-friendly format
                    items = [
                        {
                            "qty": row["qty"],
                            "ItemName": row["ItemName"],
                            "itemDescription": row["itemDescription"],
                            "amt": f"{float(row['amt']):.2f}",  # Format as two decimal places
                        }
                        for row in reader
                    ]

                    # Save JSON data to session
                    json_data = json.dumps({"items": items}, indent=2)
                    session["json_data"] = json_data
                    flash("CSV uploaded successfully! Data loaded into the form.", "success")

                except Exception as e:
                    flash(f"Failed to process CSV file: {str(e)}", "danger")

        elif action == "submit":  # Handle form submission to API
            # Extract form data
            access_key = request.form.get("accessKey")
            template_name = request.form.get("templateName")
            output_name = request.form.get("outputName", "result.pdf")
            dev_mode = request.form.get("devMode", "n")  # Default to "n"
            store_to = request.form.get("storeTo", "")

            data = request.form.get("data")

            # Validate and format the data field as proper JSON
            try:
                parsed_data = json.loads(data)  # Ensure it's valid JSON
                # The parsed_data should already contain 'items' correctly
            except json.JSONDecodeError as e:
                flash(f"Failed to process data field as JSON: {e}", "danger")
                return render_template("form.html", json_data=json_data)

            # Prepare API payload, make sure we don't wrap it in 'data'
            payload = {
                "accessKey": access_key,
                "templateName": template_name,
                "outputName": output_name,
                "devMode": dev_mode,
                "storeTo": store_to,

                "data": parsed_data  # Directly add 'items' here without wrapping in 'data'
            }

            print("Payload being sent to API:", payload)

            # API request
            api_url = "https://us1.dws4.docmosis.com/api/render"
            try:
                response = requests.post(api_url, json=payload)
                response.raise_for_status()

                # Handle successful PDF response
                if response.headers.get("Content-Type") == "application/pdf":
                    output_file_path = os.path.join(OUTPUT_DIR, output_name)
                    with open(output_file_path, "wb") as file:
                        file.write(response.content)

                    file_url = url_for("serve_file", filename=output_name, _external=True)
                    flash(f"File generated successfully! <a href='{file_url}' target='_blank'>Click here to view/download</a>", "success")
                else:
                    flash("Unexpected content type returned by API.", "danger")

            except requests.exceptions.RequestException as e:
            # Capture response details if available
                error_message = f"API request failed: {str(e)}"

            # Check if we have a response from the server
                if hasattr(e, 'response') and e.response is not None:
                    response = e.response
                    error_message += f"\nStatus Code: {response.status_code}"
                    error_message += f"\nResponse Body: {response.text}"

            # Flash the detailed error message
                flash(error_message, "danger")

    return render_template("form.html", json_data=json_data)


@app.route("/files/<filename>")
def serve_file(filename):
    """
    Serve generated files for download.
    """
    return send_from_directory(OUTPUT_DIR, filename)

@app.route('/git_update', methods=['POST'])
def git_update():
    repo = git.Repo('docmosis')
    origin = repo.remotes.origin
    repo.create_head('main',
                     origin.refs.main).set_tracking_branch(origin.refs.main).checkout()
    origin.pull()
    return '', 200


if __name__ == "__main__":
    app.run(debug=True)
