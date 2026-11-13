from flask import Flask, request
from register_preop_to_postop import handler as reg_handler

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False




@app.route("/register-preop_to_postop", methods=["POST"])
def preop_to_postop():
    event = request.json
    return reg_handler(event, "")



# WSGI入口函数
def handler(environ, start_response):
    return app(environ, start_response)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9999, threaded=False)
