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

```
Server Software:        localhost:8080
Server Hostname:        localhost
Server Port:            8080
Document Path:          /
Document Length:        36 bytes
Concurrency Level:      5
Time taken for tests:   111.930 seconds
Complete requests:      50000
Failed requests:        0
Total transferred:      9000000 bytes
HTML transferred:       1800000 bytes
Requests per second:    446.71 [#/sec] (mean)
Time per request:       11.193 [ms] (mean)
Time per request:       2.239 [ms] (mean, across all concurrent requests)
Transfer rate:          78.52 [Kbytes/sec] received
Connection Times (ms)
```

```               
               min   mean[+/-sd]    median      max              
Connect:        0       5  226.8        0        16152

Processing:     1       6  40.6         4       2524

Waiting:        1       6 39.8          4       2524

Total:          11      11 230.8        4       16167
```
```
Percentage of the requests served within a certain time (ms)
  50%      4
  66%      4
  75%      5
  80%      5
  90%      6
  95%      8
  98%     11
  99%     18
 100%  16167 (longest request)

