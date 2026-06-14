Okay, im thinking what i really want is just a centralized service and each scraper calls it to get a permit to make a request, the permits should be able to queue up to a configurable limit. when the download or request is complete, the permit is returned to the server, the server applies the backoff timer, and then issues the permit to the next service. there should be a pool of permits of configurable size per domain as well and maybe it'd be nice to have it connect to a robots.txt service and use the output as the baseline scrape limit that the user can override.

For the application architecture i'd like to use grpc bi-directional streams for minimum latency

Please build the server and client layers, include tests for both that test the expected functionality of the tool. I'd like the server to work off of a database for the configuration and i'd like to have an api for that database, and an ui so i can update the configuration in real time and override robot.txt configs. when robot.txt configs are over-written, it should be marked as an overwrite and there should be a revert button. the database can store the robots.txt files if that makes things easier, i would like the robots.txt files to expire at a configurable interval at which time a fresh one will be pulled. if no robots.txt is available we should mark the date we checked and check again at a configurable interval.

keep everyting inside this request_authorization folder, use the following folder names: 
* server
  * app
  * readme.md
* client
  * readme.md
* api
* ui

please include a docker-compose.yaml file at the root of the project that will spin up the server, api, and ui. use non standard ports, perhaps in the 9000 range, the following ports are already in use: 8000, 8010, 8020, 8080, 5432

for the server please use whatever language makes the most sense for this application, it will need to be runnable in docker
the client layer is expected to be more of a library that the scrapers can import and use
for the api fastapi is fine, please use sqlalchemy to talk to the db and use a local sqlite instance for now
for the ui please use react, i plan on eventually creating a scraper command dashboard that has uis for all cache services and this service, but for now let's keep it standalone. if the pieces are re-useable, that's a bonus

from a user perspective, i'd like to have the ability to put a bunch of domains into a bucket and then set the rate limit for that bucket. the use case here would be a bunch of cdns i could check a box next to in the ui and add to the cnd bucket, then set the per domain scrape rate to 10 requests per second with no time delay or something like that