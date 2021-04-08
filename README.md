# Simple web server



In this Simple Web Server implements epoll(linux) and kqueue(BSD, Mac OS) methods of
I/O events for TCP Socket


## Results of load testing:
This is ApacheBench, Version 2.3 <$Revision: 1879490 $>
Copyright 1996 Adam Twiss, Zeus Technology Ltd, http://www.zeustech.net/
Licensed to The Apache Software Foundation, http://www.apache.org/

Benchmarking localhost (be patient)
* Completed 5000 requests
* Completed 10000 requests
* Completed 15000 requests
* Completed 20000 requests
* Completed 25000 requests
* Completed 30000 requests
* Completed 35000 requests
* Completed 40000 requests
* Completed 45000 requests
* Finished 50000 requests


Server Software:        localhost:8080

Server Hostname:        localhost

Server Port:            8080


Document Path:          /

Document Length:        446 bytes


Concurrency Level:      100

Time taken for tests:   326.584 seconds

Complete requests:      50000

Failed requests:        89

   (Connect: 0, Receive: 0, Length: 89, Exceptions: 0)
   
Non-2xx responses:      49911

Total transferred:      30994731 bytes

HTML transferred:       22260306 bytes

Requests per second:    153.10 [#/sec] (mean)

Time per request:       653.168 [ms] (mean)

Time per request:       6.532 [ms] (mean, across all concurrent requests)

Transfer rate:          92.68 [Kbytes/sec] received


Connection Times (ms)

              min  mean[+/-sd] median   max              
Connect:        0    1  66.7      0   14904

Processing:     4  501 4074.6     18  109636

Waiting:        0  357 1701.6     18  106511

Total:          5  502 4075.4     19  109644


Percentage of the requests served within a certain time (ms)

  50%     19
  
  66%     22
  
  75%     25
  
  80%     30
  
  90%   1048
  
  95%   1455
  
  98%   3479
  
  99%   7294
  
 100%  109644 (longest request)
 
