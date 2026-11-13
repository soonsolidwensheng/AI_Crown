# -*- coding: utf-8 -*-
"""
本地 Flask 测试应用：暴露 stdcrown、postprocess、stitch_edge 三个接口，
与 Lambda handler 入参/出参一致，便于本地联调。
"""
import logging
import multiprocessing
import os
import sys
import traceback

from flask import Flask, request, jsonify
from flasgger import Swagger

# 请求处理超时（秒），可通过环境变量配置，默认 180s，超过后返回
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "180"))

app = Flask(__name__)

# 配置 Swagger
app.config['SWAGGER'] = {
    'title': 'AI Crown API',
    'uiversion': 3,
    'version': '1.0.0',
    'description': '本地 Flask 测试应用：提供 stdcrown、postprocess、stitch_edge 三个接口',
    'contact': {
        'developer': 'AI Crown Team',
        'email': 'support@aicrown.com'
    },
    'license': {
        'name': 'MIT',
        'url': 'https://opensource.org/licenses/MIT'
    },
    'tags': [
        {
            'name': 'Health',
            'description': '健康检查相关接口'
        },
        {
            'name': 'Crown Processing',
            'description': '牙冠处理相关接口'
        }
    ],
    'specs': [
        {
            'endpoint': 'apispec_1',
            'route': '/apispec_1.json',
            'rule_filter': lambda rule: True,
            'model_filter': lambda tag: True
        }
    ],
    'static_url_path': '/flasgger_static',
    'swagger_ui': True,
    'specs_route': '/apidocs/'
}

Swagger(app)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


@app.after_request
def log_request(response):
    logger.info(f"{request.method} {request.path} - {response.status_code}")
    return response


@app.route("/health", methods=["GET"])
def health():
    """
    健康检查，用于验证 Docker + Flask 是否正常运行。
    ---
    tags:
      - Health
    responses:
      200:
        description: 健康检查成功
        schema:
          id: HealthResponse
          type: object
          properties:
            status:
              type: string
              example: "ok"
    """
    return jsonify({"status": "ok"})


def _worker(module_name, handler_name, event, conn):
    """子进程：执行业务逻辑，结果写入 Pipe，完成后强制退出避免后台线程挂起。"""
    import pickle
    try:
        mod = __import__(module_name, fromlist=[handler_name])
        handler = getattr(mod, handler_name)
        result = handler(event, None)
        conn.send(pickle.dumps({"ok": True, "data": result}))
    except Exception as e:
        conn.send(pickle.dumps({"ok": False, "error": str(e), "tb": traceback.format_exc()}))
    finally:
        conn.close()
        os._exit(0)


def _call_handler(module_name, handler_name="handler"):
    """通用逻辑：子进程执行业务，主进程 poll 等待结果。
    超时时先返回 503 给客户端，响应发送完毕后进程退出，start.sh 守护循环自动重启。
    """
    import pickle

    event = request.get_json(force=True, silent=True)
    if event is None:
        return jsonify({"Code": 400, "State": "Failure", "Msg": "Invalid or missing JSON body"}), 400

    parent_conn, child_conn = multiprocessing.Pipe(duplex=False)
    proc = multiprocessing.Process(
        target=_worker,
        args=(module_name, handler_name, event, child_conn),
        daemon=True,
    )
    proc.start()
    child_conn.close()

    has_result = parent_conn.poll(REQUEST_TIMEOUT)

    if has_result:
        try:
            ret = pickle.loads(parent_conn.recv())
        except Exception as e:
            proc.kill()
            parent_conn.close()
            return jsonify({"Code": 203, "State": "Failure", "Msg": f"Failed to read result: {e}"}), 500
        proc.kill()
        parent_conn.close()

        if ret["ok"]:
            result = ret["data"]
            if isinstance(result, dict):
                return jsonify(result)
            return jsonify({"Code": 200, "State": "Success", "Msg": {"data": result}})
        else:
            logger.error(ret["tb"])
            return jsonify({"Code": 203, "State": "Failure", "Msg": ret["error"]}), 500
    else:
        # 超时：kill 业务子进程，构造 503 响应
        # 通过 response.call_on_close 注册回调：响应字节全部写入 socket 后再 os._exit
        # gunicorn master 检测到 worker 退出后自动重启新 worker
        proc.kill()
        parent_conn.close()
        logger.error(f"[TIMEOUT] {module_name} exceeded {REQUEST_TIMEOUT}s, process will restart after response...")

        resp = jsonify({
            "Code": 503,
            "State": "Timeout",
            "Msg": f"Request timeout after {REQUEST_TIMEOUT}s, service is restarting",
        })
        resp.status_code = 503

        @resp.call_on_close
        def _exit_after_send():
            logger.info("Response sent, exiting worker for restart...")
            os._exit(1)

        return resp


@app.route("/stdcrown", methods=["POST"])
def stdcrown():
    """
    标准牙冠生成接口
    ---
    tags:
      - Crown Processing
    parameters:
      - name: body
        in: body
        required: true
        schema:
          id: StdCrownRequest
          type: object
          description: 标准牙冠生成请求参数
    responses:
      200:
        description: 标准牙冠生成成功
        schema:
          id: StdCrownSuccessResponse
          type: object
          properties:
            Code:
              type: integer
              example: 200
            State:
              type: string
              example: "Success"
            Msg:
              type: object
      203:
        description: 标准牙冠生成失败
        schema:
          id: StdCrownErrorResponse
          type: object
          properties:
            Code:
              type: integer
              example: 203
            State:
              type: string
              example: "Failure"
            Msg:
              type: string
    """
    return _call_handler("stdcrown")


@app.route("/postprocess", methods=["POST"])
def postprocess():
    """
    后处理接口
    ---
    tags:
      - Crown Processing
    parameters:
      - name: body
        in: body
        required: true
        schema:
          id: PostprocessRequest
          type: object
          description: 后处理请求参数
    responses:
      200:
        description: 后处理成功
        schema:
          id: PostprocessSuccessResponse
          type: object
          properties:
            Code:
              type: integer
              example: 200
            State:
              type: string
              example: "Success"
            Msg:
              type: object
      203:
        description: 后处理失败
        schema:
          id: PostprocessErrorResponse
          type: object
          properties:
            Code:
              type: integer
              example: 203
            State:
              type: string
              example: "Failure"
            Msg:
              type: string
    """
    return _call_handler("postprocess")


@app.route("/stitch_edge", methods=["POST"])
def stitch_edge():
    """
    边缘缝合接口
    ---
    tags:
      - Crown Processing
    parameters:
      - name: body
        in: body
        required: true
        schema:
          id: StitchEdgeRequest
          type: object
          description: 边缘缝合请求参数
    responses:
      200:
        description: 边缘缝合成功
        schema:
          id: StitchEdgeSuccessResponse
          type: object
          properties:
            Code:
              type: integer
              example: 200
            State:
              type: string
              example: "Success"
            Msg:
              type: object
      203:
        description: 边缘缝合失败
        schema:
          id: StitchEdgeErrorResponse
          type: object
          properties:
            Code:
              type: integer
              example: 203
            State:
              type: string
              example: "Failure"
            Msg:
              type: string
    """
    return _call_handler("stitch_edge")


if __name__ == "__main__":
    # spawn 模式：子进程干净启动，避免 waitress 多线程环境下 fork 继承锁导致死锁
    multiprocessing.set_start_method("spawn", force=True)
    from waitress import serve
    # threads=1：单线程处理请求，与超时重启机制配合（进程退出后 start.sh 重启）
    serve(app, host="0.0.0.0", port=5000, threads=1)
