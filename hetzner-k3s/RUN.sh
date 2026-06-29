#
# References:
# - https://vitobotta.github.io/hetzner-k3s/Creating_a_cluster/
#


# wget https://github.com/vitobotta/hetzner-k3s/releases/latest/download/hetzner-k3s-linux-amd64 -O ~/bin/hetzner-k3s
# krel_stable=$(curl -L -s https://dl.k8s.io/release/stable.txt)
# curl -LO --output-dir ~/bin "https://dl.k8s.io/release/$krel_stable/bin/linux/amd64/kubectl" 
# curl -LO --output-dir ~/bin "https://dl.k8s.io/release/$krel_stable/bin/linux/amd64/kubectl-convert" 
# (cd ~/bin; chmod a+x hetzner-k3s kubectl*)
# curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-4 | bash -x

hetzner-k3s create --config cluster.yaml | tee create.log



