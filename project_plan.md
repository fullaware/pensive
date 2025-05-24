# Asteroid Mining Operation Simulator Project Plan

## Vision

I want to build a simulation where you mine asteroids for money and the further development of space exploration. AIs are a powerful ally in our reach for the stars. Dwarf Fortress + AI co-operation + Space Mining Operation Simulator.

I need to hand this well documented API over to an LLM to manipulate variables for each day of mining to greater simulate challenges that may cause delays, which costs money, not to mention you have to survive getting hit with microparticles and others may not be so micro.

## Features

### AI Management
- AIs will pilot ships, mine asteroids, and manage resources.
- The user will be able to direct the AI on how to manage the resources, or not.
- The AI will provide feedback on how the user's strategy is working.
- The user will be able to see the market trends and adjust their strategy.

### Mining Simulation
- During this day you will have 24 hours to mine resources from the asteroid.
- `mine_asteroid.py` explains how we can simulate mining per hour. That will be our finest measurement of time, 1 hour.
- The amount of material we mine is measured in kg.
- How much we can mine per hour is randomized, but I would like an LLM to assess each hour's output and "explain" why certain things may not have met expectations.
- We want to provide graphs to the users to help them change their strategy for what elements to focus on.
- The user may choose to purge a bunch of "worthless" platinum when the market shifts and another element is on the rise.

### Company Management
- Every user is the CEO of their own space mining company.
- Companies will be ranked based on their total value AND their totals of each element mined.
- Each element mined will have certain use cases that it is associated with which we have limited to 12: "fuel", "lifesupport", "energystorage", "construction", "electronics", "coolants", "industrial", "medical", "propulsion", "shielding", "agriculture", "mining".
- The simulator can be expanded into those 12 use cases in later versions.

### Mission Planning
- You have to build a mission plan for each asteroid you mine, each mission costs money so we are going to have to choose our asteroid wisely.
- The longer we are in space, the longer we are exposed to things that could go wrong.
- `find_asteroids.py` will allow the user to find real asteroids by name and distance from Earth in days.
- Once the user has selected the asteroid, we will use its distance from Earth in `moid_days` to calculate the mission duration.
- While travel to and from the asteroid is mostly static, the number of days you allocate to mining may need to be a variable.
- If you only allow for 10 days of mining, but you aren't getting the yield you want, you may want to extend the mission. This will increase the risk of something going wrong, but it may also increase the reward. The user will have to balance the risk and reward of each mission and so will the investors.

### Funding and Investment
- Once you have your mission plan, you have to fund it.
- You will publish your mission plan to the AI who will evaluate it and then authorize your investment with an expected return on investment of 1.25x.
- If you cannot make it back to Earth with the ship intact it's not "Game Over", it just means your next funding round is going up to 1.5x, and so on.
- The long-term goal is to have enough money to fund your own missions without needing investors.

### User Experience
- The user experience should be click, read what has happened, click, read what has happened.
- They can click to modify which elements should be mined. But without guidance, it will mine and collect all elements it can get because the leaderboard is based on total elements mined, not just company value.
- The simulation should be automated as much as possible, it's to show how much we can rely on AI to drive business decisions.
- The user should be able to see the AI's decision-making process and be able to adjust it.
- The AI should be able to explain why it made the decisions it did.
- The user should be able to see the market trends and adjust their strategy.
- The user should be able to see the leaderboard and see how they rank against other companies.

### Minimum Viable Product
- Python, Ollama, OpenAI, MongoDB, FastAPI, Pydantic-ai
- .env file for MONGODB_URI OLLAMA_MODEL OLLAMA_URI
- Logging to stdout, colorful logging
- **All numerical values should be stored as `INT64` or `$numberLong` in MongoDB to handle large numbers safely.**
- **All references to _id fields should be typed ObjectId.**