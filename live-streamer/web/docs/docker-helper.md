# Docker helper

## Building the container

Run the following command to build the web app in docker when on the target machine from the `/web` dir:

`docker build -t live-streamer-web .`

## Running the container

Run from the same dir `web`:

`docker run -d -p 3000:3000 --name live-streamer live-streamer-web`

Then access it at
`http://<linux-machine-ip>:3000`

## Useful Commands

### Display logs

`docker logs <container-name>`

### Follow logs

`docker logs -f <container-name>`

### Start/Stop container

`docker start <container-name>`
`docker stop <container-name>`

# Building and running both the web & server

## Web

`docker build -t live-streamer-web ./web`

## server

`docker build -t live-streamer-server ./server`

# Run the container in dummy mode (using the local file rather than IP camera)

`docker-compose up`
