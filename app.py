import os
import shlex
import subprocess
import time

from celery import Celery
from flask import Flask, request, jsonify, send_from_directory, abort, render_template_string
from flask_cors import CORS
from werkzeug.security import safe_join

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
def generate_3d_object_task(self, prompt, save_path, model="DG"):
    """
    Generate a 3D object based on the prompt and save it to the specified path.
    :param self:
    :param prompt:
    :param save_path:
    :param model: select the model to use for generation. The model can be
    "DG" for DreamGaussian
    "MV" for MVDream
    :return:
    """
    command_echo = f"echo 'Generating 3D object for prompt: {prompt}'"

    escaped_prompt = shlex.quote(prompt)
    escaped_save_path = shlex.quote(save_path)
    if model == "DG":
        command_stage1 = f"python main.py --config configs/text.yaml prompt={escaped_prompt} save_path={escaped_save_path}"
        command_stage2 = f"python main2.py --config configs/text.yaml prompt={escaped_prompt} save_path={escaped_save_path}"
    elif model == "MV":
        command_stage1 = f"python main.py --config configs/text_mv.yaml prompt={escaped_prompt} save_path={escaped_save_path}"
        command_stage2 = f"python main2.py --config configs/text_mv.yaml prompt={escaped_prompt} save_path={escaped_save_path}"
    else:
        return {"error": "Invalid model", "details": f"Model {model} is not supported"}
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
    model = data.get('model', 'DG')
    save_path = data.get('save_path', 'default_path')
    save_path = save_path + "_" + model

    if not prompt:
        return jsonify({"error": "Prompt is required"}), 400

    # check if the save_path exists in folder logs/{save_path}.obj
    if os.path.exists(f'logs/{save_path}.obj'):
        return jsonify({"message": "3D object already exists",
                        "object_path": f'logs/{save_path}.obj',
                        "task_id": "0000"}), 200

    print("Starting task")
    task = generate_3d_object_task.apply_async(args=[prompt, save_path, model])
    return jsonify({"task_id": task.id}), 202


@app.route('/task-status/<task_id>', methods=['GET'])
def task_status(task_id):
    if task_id == "0000":
        return jsonify({"message": "3D object already exists",
                        "task_id": "0000"}), 200

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
        # Get full paths along with their creation times
        files_with_paths = [(file, os.path.getctime(os.path.join(LOG_DIR, file))) for file in files]
        # Sort files by creation time, newest first
        files_sorted = sorted(files_with_paths, key=lambda x: x[1], reverse=True)
        # Generate HTML content with links to the files and their creation dates in a table
        file_rows = [
            f'<tr><td><a href="/logs/{file}">{file}</a></td><td>{time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(creation_time))}</td></tr>'
            for file, creation_time in files_sorted
        ]
        file_table_html = f'<table><tr><th>File Name</th><th>Creation Date</th></tr>{" ".join(file_rows)}</table>'
        return render_template_string(f"""<h1>Log Files</h1>{file_table_html}""")
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
