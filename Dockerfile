FROM harbor.emea.ocp.int.kn/dockerhub/library/python:3.11.1
##########
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG http_proxy
ARG https_proxy
ARG use_proxy
##########
ENV HTTP_PROXY $HTTP_PROXY
ENV HTTPS_PROXY $HTTPS_PROXY
ENV http_proxy $http_proxy
ENV https_proxy $https_proxy
ENV use_proxy $use_proxy
##########
WORKDIR /usr/p2papi
COPY requirements.txt ./
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONPATH "${PYTHONPATH}:/app"
CMD [ "python", "./app/main.py" ]
