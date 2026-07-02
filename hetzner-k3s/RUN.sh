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

hetzner-k3s create --config k1-cluster.yaml | tee create.log


# master1_ip=$(hcloud server ip k1-master1)
# scp root@$master1_ip:/etc/rancher/k3s/k3s.yaml /home/jw/.kube/config
# sed -i -e 's/127.0.0.1/api-k1.jwqa.de/' ~/.kube/config
cp kubeconfig ~/.kube/config

kubectl get nodes
 ...

kubectl apply -f 2.0.0/check_mk_rbac.yaml
kubectl get serviceaccounts check-mk -n check-mk -o yaml
 ...
kubectl get secrets -n check-mk
	-> nothing.

# Starting with Kubernetes 1.24, the automatic creation of permanent Secret tokens for ServiceAccounts was removed
# we need to manually create a secret:
#
## short lived token: kubectl create token check-mk -n check-mk

## permanent token:
kubectl apply -f - <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: check-mk-token
  namespace: check-mk
  annotations:
    kubernetes.io/service-account.name: check-mk
type: kubernetes.io/service-account-token
EOF

kubectl get secrets check-mk-token -n check-mk -o jsonpath='{.data.ca\.crt}' | base64 --decode > 2.0.0/ca.crt
kubectl get secrets check-mk-token -n check-mk -o jsonpath='{.data.token}' | base64 --decode > 2.0.0/token

 -> Setup > General > Global settings > Site Management > Trusted certificate authorities for SSL
	-> add the ca.crt

 -> Setup > General > Passwords > Add password e.g. under the ID kubernetes: (token, all in one line!)

-> setup create folder k8s-objects, there add host api-k1.jwqa.de

-> Setup > Agents > VM, Cloud, Container > Kubernetes
  -> create rule in folder: select k8s-objects, 
	-> click on "Create rule in folder:"
	-> show more -> [x] restrict source hosts	... so that we can manage multiple clusters...


---- nothing hapens. no new services... BAD.
docker exec -ti monitoring bash
omd su cmk
cmk -D api-k1.jwqa.de
 Addresses:              95.217.171.93
 Tags:                   [address_family:ip-v4-only], [agent:cmk-agent], [criticality:prod], [ip-v4:ip-v4], [networking:lan], [piggyback:auto-piggyback], [site:cmk], [snmp_ds:no-snmp], [tcp:tcp]
 Labels:                 
 Host groups:            check_mk
 Contact groups:         all
 Agent mode:             Normal Checkmk agent, or special agent if configured
 Type of agent:          
   Program: /omd/sites/cmk/share/check_mk/agents/special/agent_kubernetes '--pwstore=2@0@kubernetes' '--token' '**********************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************************' '--infos' 'nodes,ingresses,deployments,pods,endpoints,daemon_sets,stateful_sets,jobs' '--api-server-endpoint' 'https://api-k1.jwqa.de:6443'
   Process piggyback data from /omd/sites/cmk/tmp/check_mk/piggyback/api-k1.jwqa.de
 Services:
   checktype item params description groups
   --------- ---- ------ ----------- ------

# we can try this command manually.

with --debug, we get:

return self.api_client.call_api('/apis/extensions/v1beta1/ingresses', 'GET')

lumo says:
CheckMK 2.0.0 is too old. Its Kubernetes special agent was written when extensions/v1beta1 was still the standard Ingress API. It has not been updated to use the newer networking.k8s.io/v1 API path.
The Fix: Upgrade CheckMK

You need to upgrade your CheckMK instance to at least 2.1.x (preferably 2.3.x, which you mentioned your central instance is running). Starting around version 2.1, the Kubernetes special agent was updated to query networking.k8s.io/v1 instead of the removed extensions/v1beta1

vi /var/lib/docker/overlay2/*/merged/opt/omd/versions/2.0.0p39.cee/lib/python3/cmk/special_agents/agent_kubernetes.py
1194         services: Iterator = core_api.list_service_for_all_namespaces().items
1195         ingresses: Iterator = [];     # JW; ext_api.list_ingress_for_all_namespaces().items
1196         try:

-> now the discovery works.
