cache browser, we've built webcache, imgcache, filecache, and vidcache, time to make a centralized browser to view/navigate all of the content. a few notes, this will likely need to be an api and a ui minimum, i'd like to incorporate it into the scrape_stack as the primary front end, we'll leave the request auth ui alone, deal with it later. 

all of the caches have content streaming routes built in specifically for this application, there is a lot of content in the caches so i want to make sure the solution we develop will be very robust and allow for navigation without crashing the browser or too much lag.

We architected all of the storage such that there's a bucket and a prefix and the content goes within the prefix folder. the browser should handle this navigation structure

cache results handling:

for all cache results the ui should provide the means for a global search, search within bucket/bucket+prefix, date filters/sorting, and scrape job filters. there should also be a means for users to see and interact with the history of any cache item as well

filecache results: Provide download link in ui that allows user to download a copy of the cached file locally
webcache results: allow users to view and search the text content
imgcache resutls: allow users to view and download images, users shouls also be able to change the grid size so fewer large images will be rendered or more small images in the display grid
vidcache results: same as imgcache browser but for videos, users should be able to play videos from the grid simultaneously or open a single video to full-screen