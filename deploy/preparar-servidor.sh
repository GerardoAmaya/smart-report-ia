#!/bin/sh
# Prepara una maquina Ubuntu recien creada para correr el despliegue.
#
# Se corre en el servidor, una vez, y se puede repetir sin romper nada: cada
# paso mira primero si ya esta hecho. Existe para que rehacer la maquina —si
# Oracle la recupera o hay que mudarse— sea un comando y no una tarde.
#
#   ssh ubuntu@IP 'sh -s' < deploy/preparar-servidor.sh
set -eu

echo "== Puertos 80 y 443 en el firewall de la propia maquina"
# Las imagenes de Ubuntu de Oracle traen iptables que rechaza todo salvo SSH.
# Abrir solo en la consola de Oracle no basta: el sitio no contesta y parece
# que falla Caddy. Se insertan **antes** de la regla REJECT, no al final, donde
# no llegaria nada.
for puerto in 80 443; do
  if ! sudo iptables -C INPUT -p tcp -m state --state NEW --dport "$puerto" -j ACCEPT 2>/dev/null; then
    linea="$(sudo iptables -L INPUT --line-numbers -n | awk '/REJECT/ {print $1; exit}')"
    sudo iptables -I INPUT "${linea:-1}" -p tcp -m state --state NEW --dport "$puerto" -j ACCEPT
  fi
done
# Se guarda **antes** de instalar Docker: guardar despues persistiria tambien
# las cadenas que Docker crea al arrancar, y al reiniciar chocarian con las suyas.
sudo netfilter-persistent save >/dev/null

echo "== Actualizaciones de seguridad automaticas"
# Una maquina en internet sin parches es la forma mas comun de perderla.
sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq unattended-upgrades ca-certificates curl >/dev/null
sudo dpkg-reconfigure -f noninteractive unattended-upgrades

echo "== Docker, desde el repositorio oficial"
# No el paquete docker.io de Ubuntu: va atrasado y sin el plugin de compose v2.
if ! command -v docker >/dev/null; then
  sudo install -m 0755 -d /etc/apt/keyrings
  sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  sudo chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null
fi
sudo usermod -aG docker "$USER"

# Los registros de los contenedores crecen sin limite por defecto, y en una
# maquina que corre sola meses se comen el disco sin que nadie mire.
if [ ! -f /etc/docker/daemon.json ]; then
  printf '{\n  "log-driver": "json-file",\n  "log-opts": {"max-size": "10m", "max-file": "5"}\n}\n' \
    | sudo tee /etc/docker/daemon.json >/dev/null
  sudo systemctl restart docker
fi

echo "== Swap de 2 GB"
# Compilar el tablero pide memoria a rafagas; sin swap, un pico mata el build
# con un error que no dice que fue la memoria.
if ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile >/dev/null
  sudo swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

echo "== Listo"
docker --version
docker compose version
sudo iptables -L INPUT -n --line-numbers | grep -E 'dpt:(22|80|443)|REJECT'
swapon --show
