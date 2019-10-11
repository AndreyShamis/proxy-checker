# Proxy Checker

Use http://spys.one/proxys/UA/ in order to get proxy list

copy table column in format
~~~
1 46.219.14.37:30686
2 91.225.5.43:40171
3 62.122.201.241:46176
4 91.205.218.33:80
5 154.41.4.173:8081
~~~
or
~~~
46.219.14.37:30686
91.225.5.43:40171
62.122.201.241:46176
91.205.218.33:80
154.41.4.173:8081
~~~
and save it in same directory as proxylist.txt

Run the script 
~~~ bash
python main.py
~~~



For download

bash
export cmd_prms="--limit-rate 2M --retries 3 --no-check-certificate --prefer-insecure https://www.youtube.com/watch?v=DY30Kf19Puk"; export PROX="91.217.5.146:8080"; youtube-dl --proxy="${PROX}" ${cmd_prms}; export PROX="82.144.205.109:3128"; youtube-dl --proxy="${PROX}" ${cmd_prms}; sleep 60; export PROX="91.217.5.146:8080"; youtube-dl --proxy="${PROX}" ${cmd_prms}; export PROX="82.144.205.109:3128"; youtube-dl --proxy="${PROX}" ${cmd_prms}; sleep 60; export PROX="91.217.5.146:8080"; youtube-dl --proxy="${PROX}" ${cmd_prms}; export PROX="82.144.205.109:3128"; youtube-dl --proxy="${PROX}" ${cmd_prms}; sleep 60; export PROX="91.217.5.146:8080"; youtube-dl --proxy="${PROX}" ${cmd_prms}; export PROX="82.144.205.109:3128"; youtube-dl --proxy="${PROX}" ${cmd_prms}; sleep 60; export PROX="91.217.5.146:8080"; youtube-dl --proxy="${PROX}" ${cmd_prms}; export PROX="82.144.205.109:3128"; youtube-dl --proxy="${PROX}" ${cmd_prms}; sleep 60; export PROX="91.217.5.146:8080"; youtube-dl --proxy="${PROX}" ${cmd_prms}; export PROX="82.144.205.109:3128"; youtube-dl --proxy="${PROX}" ${cmd_prms}; sleep 60;
export proxy="91.225.226.39:35269"; export https_proxy=$proxy; export http_proxy=$proxy; echo "HTTP:"$http_proxy; echo "HTTPS:"$https_proxy; youtube-dl  --no-check-certificate --prefer-insecure https://www.youtube.com/watch?v=VXOjcxhevlM
or
export proxy=""; export https_proxy=$proxy; export http_proxy=$proxy; echo "HTTP:"$http_proxy; echo "HTTPS:"$https_proxy; youtube-dl  https://www.youtube.com/watch?v=VXOjcxhevlM

