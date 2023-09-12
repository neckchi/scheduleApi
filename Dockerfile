FROM harbor.emea.ocp.int.kn/dockerhub/library/python:3.11.1

WORKDIR /usr/p2papi

COPY requirements.txt ./

RUN pip install --proxy http://zscaler.proxy.int.kn:80 --upgrade pip
RUN pip install --proxy http://zscaler.proxy.int.kn:80 --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH "${PYTHONPATH}:/app"

CMD [ "python", "./app/main.py" ]
