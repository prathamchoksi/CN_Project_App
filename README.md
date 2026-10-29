# Two-pod Raspberry Pi demo

- **Database pod** (Postgres) on the database Pi. Stores one value: `hello world`.
- **Backend pod** (Flask) on the backend Pi. On each request it reads the value from the database and returns it.

## Deploy

```bash
# label the nodes
kubectl label node <db-pi-name>      role=database
kubectl label node <backend-pi-name> role=backend

# build image and load it into k3s on the backend Pi
docker build -t backend-api:latest .
docker save backend-api:latest | sudo k3s ctr images import -

kubectl apply -f k8s-manifests.yaml
kubectl get pods -o wide

curl http://<backend-pi-ip>:30080/
# {"value":"hello world"}
```
