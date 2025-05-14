
# Define custom function directory
FROM python:3.8.18 AS build-image
ARG FUNCTION_DIR="/function"
# ARG WORK_DIR="/crown_cpu"
# 使用基础镜像
# Include global arg in this stage of the build
ARG FUNCTION_DIR
ARG WORK_DIR
RUN mkdir -p ${FUNCTION_DIR}
COPY . ${FUNCTION_DIR}

COPY ./requirements.txt ${FUNCTION_DIR}/requirements.txt
RUN pip install -r ${FUNCTION_DIR}/requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple


# RUN echo "deb https://mirrors.tuna.tsinghua.edu.cn/debian/ bookworm main" > /etc/apt/sources.list
# RUN echo "deb-src https://mirrors.tuna.tsinghua.edu.cn/debian/ bookworm main" >> /etc/apt/sources.list

# Install additional packages
RUN apt-get update && apt-get install -y\
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

RUN mv ${FUNCTION_DIR}/remesh.py /usr/local/lib/python3.8/site-packages/trimesh/remesh.py
# Set working directory to function root directory
WORKDIR ${FUNCTION_DIR}
ENV LD_LIBRARY_PATH=${FUNCTION_DIR}

EXPOSE 9999
CMD [ "python deploy.py" ]



