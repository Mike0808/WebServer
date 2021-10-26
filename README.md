# Simple web server

In this Simple Web Server implements epoll(linux) and kqueue(BSD, Mac OS) methods of
I/O events for TCP Socket.
For this task taked third-party model asyncore_epoll with little bit changes for SO_REUSEPORT insted SO_REUSEADDR


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

```
Server Software:        localhost:8080
Server Hostname:        localhost
Server Port:            8080
Document Path:          /
Document Length:        36 bytes
Concurrency Level:      100
Time taken for tests:   103.114 seconds
Complete requests:      50000
Failed requests:        0
Total transferred:      9000000 bytes
HTML transferred:       1800000 bytes
Requests per second:    484.90 [#/sec] (mean)
Time per request:       206.227 [ms] (mean)
Time per request:       2.062 [ms] (mean, across all concurrent requests)
Transfer rate:          85.24 [Kbytes/sec] received
Connection Times (ms)
```

```               
               min   mean[+/-sd]    median      max              
Connect:        0       88 1178.0      0        21543
Processing:     1       101 159.1      81       2472
Waiting:        1       101 158.8      80       2471
Total:          1       189 1182.9     81       21550

```
```
Percentage of the requests served within a certain time (ms)
  50%      81
  66%      86
  75%      89
  80%      92
  90%      101
  95%      133
  98%      798
  99%      1390
 100%      21550 (longest request)

it