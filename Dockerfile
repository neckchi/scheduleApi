FROM harbor.emea.ocp.int.kn/dockerhub/library/python:3.11.1

WORKDIR /usr/p2papi

COPY requirements.txt ./

RUN pip install --upgrade pip --proxy http://zscaler.proxy.int.kn:80 
RUN pip install --no-cache-dir -r requirements.txt --proxy http://zscaler.proxy.int.kn:80 

COPY . .

ENV PYTHONPATH "${PYTHONPATH}:/app"

CMD [ "python", "./app/main.py" ]
