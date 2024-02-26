import os
import subprocess

from celery import Celery
from flask import Flask, request, jsonify, send_from_directory, abort, render_template_string
from flask_cors import CORS
from werkzeug.security import safe_join
import shlex

app = Flask(__name__)
# Configure Celery to use Redis as the message broker
app.config['CELERY_BROKER_URL'] = 'redis://localhost:6379/0'
app.config['CELERY_RESULT_BACKEND'] = 'redis://localhost:6379/0'

# Initialize Celery
celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'])
celery.conf.update(app.config)

# Enable Cors
cors = CORS(app, resources={r"/logs/*": {"origins": "*"}})


@celery.task(bind=True)
def generate_3d_object_task(self, prompt, save_path):
    command_echo = f"echo 'Generating 3D object for prompt: {prompt}'"

    escaped_prompt = shlex.quote(prompt)
    escaped_save_path = shlex.quote(save_path)

    command_stage1 = f"python main.py --config configs/text.yaml prompt={escaped_prompt} save_path={escaped_save_path}"
    command_stage2 = f"python main2.py --config configs/text.yaml prompt={escaped_prompt} save_path={escaped_save_path}"

    print("Executing subprocess")

    try:
        # Assuming you're executing this within the 'vivify' environment
        subprocess.run(command_echo, check=True, shell=True, executable='/bin/bash')
        subprocess.run(command_stage1, check=True, shell=True, executable='/bin/bash')
        subprocess.run(command_stage2, check=True, shell=True, executable='/bin/bash')

        object_path = f'log/{save_path}'
        print(f"Subprocess executed successfully. Object path: {object_path}")

        return {"message": "3D object generated successfully", "object_path": object_path}
    except subprocess.CalledProcessError as e:
        self.update_state(state='FAILURE', meta={'exc': str(e)})
        return {"error": "Failed to generate 3D object", "details": str(e)}


# A placeholder task for checking the status of the task
@celery.task(bind=True)
def tmp_task(self, prompt, save_path):
    print("Executing tmp task")
    # time.sleep(5)
    return {"message": "Task executed successfully"}


@app.route('/generate-3d-object', methods=['POST'])
def generate_3d_object():
    print("Request received")
    data = request.json
    prompt = data.get('prompt')
    save_path = data.get('save_path', 'default_path')
    if not prompt:
        return jsonify({"error": "Prompt is required"}), 400
    print("Starting task")
    task = generate_3d_object_task.apply_async(args=[prompt, save_path])
    return jsonify({"task_id": task.id}), 202


@app.route('/task-status/<task_id>', methods=['GET'])
def task_status(task_id):
    task = generate_3d_object_task.AsyncResult(task_id)
    print("Task info:", task.info)

    if task.state == 'PENDING':
        response = {
            'state': task.state,
            'status': 'Pending...'
        }
    elif task.state != 'FAILURE':
        response = {
            'state': task.state,
            'status': task.info.get('status', ''),
            'result': task.info
        }
    else:
        # something went wrong in the background job
        response = {
            'state': task.state,
            'status': str(task.info),  # this is the exception raised
        }
    return jsonify(response)


"""
Accessing the created 3D objects
"""


@app.route('/')
def index():
    try:
        # List all files in the LOG_DIR
        files = os.listdir(LOG_DIR)
        # Generate HTML content with links to the files
        file_links = [f'<li><a href="/logs/{file}">{file}</a></li>' for file in files]
        file_list_html = '<ul>' + ''.join(file_links) + '</ul>'
        return render_template_string(f"""<h1>Log Files</h1>{file_list_html}""")
    except Exception as e:
        return str(e), 500


# Assuming the 'logs' directory is in the same directory as this script
LOG_DIR = os.path.join(os.path.dirname(__file__), 'logs')


@app.route('/logs/<filename>')
def serve_log_file(filename):
    # Ensure the filename is safe to use
    try:
        # This prevents accessing directories outside the LOG_DIR
        safe_path = safe_join(LOG_DIR, filename)
    except ValueError:
        # If the path is not safe, return a 404 not found response
        abort(404)

    # Send the file from the safe path
    return send_from_directory(LOG_DIR, filename)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
