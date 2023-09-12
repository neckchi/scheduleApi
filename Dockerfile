FROM harbor.emea.ocp.int.kn/dockerhub/library/python:3.11.1
ENV HTTPS_PROXY="http://zscaler.proxy.int.kn:80"
ENV HTTP_PROXY="http://zscaler.proxy.int.kn:80"
ENV NO_PROXY="localhost,.int.kn" 
WORKDIR /usr/p2papi

COPY requirements.txt ./
RUN env
RUN pip install --upgrade pip 
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH "${PYTHONPATH}:/app"

CMD [ "python", "./app/main.py" ]
