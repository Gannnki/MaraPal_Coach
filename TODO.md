# MaraPal Coach roadmap

## Next

- [ ] Add more questions to the retrieval evaluation dataset.
- [ ] Improve the race registration status data, maybe with all europe wide races or global races

## Later
- [ ] Run the containers as non-root users.
- [ ] Decide how long monitoring data should be kept.

## Deployment
MaraPal Coach currently runs on localhost with Docker Compose. I use ngrok
to give it a public HTTPS URL, so the demo only works when my computer is online.

I am not doing cloud deployment now because of the cost. I can reconsider AWS
or another hosting option later if MaraPal becomes part of our final big product(MaraPal), please stay tuned if you are interested.
