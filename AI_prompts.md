# AI Prompts

## Problem 1

**Prompt:**

Today we will work in homework 4. Begin by creating AI_prompts.md and put it in the homework 4 folder one section in the md file per problem (problems 1-13). each section will contain the problem number (1-13), a placeholder for the prompt, and a second placeholder for a follow-up prompt if needed. also input the attached file into the homework 4 folder.


## Problem 2

**Prompt:**

i need to understand the fields of each table in data/campus_customs.db , especially catalogue, inventory, and users. start the file output/harness.md and write down in it each table and its fields, and one short line on why each field matters for the shop or the chatbot.


## Problem 3

**Prompt:**

ok now we are going to scaffold a react / vite / typescript front end for our own campus customs site. it must include a nav bar at the top that links to the main pages: home, products, about us, log in, create account. visit the website yalebulldogblue.com to pull campus customs-style wording for home and about us, but do not copy the text there. instead i want you to write your own home and about us pages. be creative with the content, we are trying to target preppy east coasters who like squash and skiing killington and marthas vineyard. on the products page, show product images from the catalog (use the image paths in the database) with basic product info (name, price, short description). Make each product open a single-item page (large image on one side, full product text on the other including description, price, sizes/stock when you have them). clicking a card on products should take the shopper there. addd a chat interface in the bottom right of the site (a floating chat panel is fine). It does not need to talk to an agent yet, you can just make a stub that will call my backend later. you can start a simple fastAPI app in backend/main.py just to serve products and images, later not now we will grow it into the agent backend.


## Problem 4

**Prompt:**

now build a normal create-account / login flow. create account should require first name, last name, email, and password, with an additional confirm password field. then once an account is created the log in fields will be email and password. new accounts go into the users table and make sure to store passwords securely so hackers cannot access them (including both human and ai hackers). then utilize the test user in the seed database to confirm that you can log in as that user and that a brand new account you create works. the test user's credentials are test@campuscustoms.yale.edu and password is password. finally, update output/harness.md with how auth works including what you store for a user and how passwords are protected.


## Problem 5

**Prompt:**

ok now build the shop chatbot as a pydanticAI agent behind fastAPI, plugged into your front-end chat widget. put the API app in backend/main.py and it will be the file you run with Uvicorn. Keep the agent as these four files next to it: backend/prompts/prompt.md , backend/agent.py , backend/tools.py , and backend/models.py . in main.py expose a chat route so a message from the website returns a reply from the agent and whatever else you need for products/auth. For the AI model API key for the agent, you can use PORTKEY_API_KEY. put campus customs voice and safety basics into prompts/prompt.md . be thorough in the safety precautions. start or update types in models.py for chat replies and product cards as needed. in output/harness.md note how the front end talks to FastAPI and how the agent is loaded (prompt file and model). Be very specific. make sure the backend runs from the backend/ folder like this: uvicorn main:app --reload --port 8000 

**Follow-up prompt (if needed):**

i want to install the FastAPI, PydanticAI, and the OpenAI client but when you tried to do it you were trying to use untrsutworthy third party code. can't you build this from scratch without making this a security issue? and then once dependencies are installed, use the README’s commands to launch and test the backend.

## Problem 6

**Prompt:**

build any necessary agentic tools that look up real information from campus_customs.dg , including product description, price, and how many are in the stock (by size when the customer asks). the agent must use the database. no inventing prices or quantities. if a size is out of stock, say so clearly. expand prompts/prompt.md so the agent knows to call all the tools you built for price and stock questions. add or update return types in models.py . in output/harness.md , list each tool and explain which model fields you chose for lookup results and why. be detailed and thorough


## Problem 7

**Prompt:**

ok now add the following feature: when a customer asks about a type of item for example "what hoodies do you have?" the agent should search the catalogue and the website should dynamically show those matching items as product cards (image, name, price, short info) this is an API contract: the agent returns structured product matches and then the front end renders them on the website. after the dynamic product cards are loaded by your new feature, make sure the same single-item page behavior from the product page still works: each product card including hte ones the chat just put on the page should still open that detail view (large image and full info) when clicked. update prompts/prompt.md and output/harness.md so it is clear how search results reach the page.


## Problem 8

**Prompt:**

when a shopper is logged in save their chat history in the database in an appropriate table and reload it when they return. the agent should know who is chatting (name, email). put that in agent deps or an equivalent clear pattern and any necessary tools the agent can call. also pass enough page context that if someone is on a product page and asks "do you have this in yellow" the agent knows which item they mean. guests can still chat but history only needs to persist for logged-in users. document in output/harness.md how the userchat history is stored, what customer fields the agent sees , and how page context is passed. 


## Problem 9

**Prompt:**

now that the core shop works improve it by implementing these aesthetic improvements on the front end: make the aesthetic of the site match that of a scandanavian art gallery (futurism, clean, sleek, visually intriguing) and also clarify button placement so that the user is visually directed toward the most likely desired content. then brainstorm two backend agentic improbements that make the agent output better, more accurate, and safer. these can be new tools that make the agent both cheaper and faster, and implement them. then write output/usability.md as you build for each improvement say what you added and why it helps a campus customs shopper or the business. then audit the improvements and make sure they actually show up in the running app.

**Follow-up prompt (if needed):**

let's also add an improved filter on the product collection page. right now there are too many awkward filters let's just do t-shirts, jackets and hoodies, sweaters and sweatshirts. and fit everything into those categories

## Problem 10

**Prompt:**

ok now let's make this stylish. i actually hate the minimalist scandinavian art gallery aesthetic, let's change it up and make it spooky for halloween time, but keeping a real campus customs storefront vibe. specifically i want on the landing page to generate film noir artsy video in the background which contains people in yale merch in horror film like settings. i also want there to be a pop up ad that advertises spooky good prices. maybe make handsome dan the dog but in haloween yale merch as decor. color palate moody. then write output/design.md and have it say what you changed and why it should help customers stick around and buy. make it short and concrete.

**Follow-up prompt (if needed):**

i want the font of night falls bulldogs rise to be spookier like dripping with blood and i want there to be some kind of animation like spider webs 

## Problem 11

**Prompt:**

ok now test the live site and document it in output/app_check.html (a page i can double-click open). include the following screenshots I'm attaching along with short captions for chat checking the inventory level of an item, dynamic search-result cards appearing after a category question, and the updated usability features i added (updating the filters for the products). this HTML needs to be easy to grade so heading for each check, screenshot, and one or two sentences on what the screenshot proves. put the screenshot image files i'm attaching here in output/app_check_images/ and link them from app_check.html with relative paths for example app_check_images/inventory.png . 



## Problem 12

**Prompt:**

ok now keep an append-only output/audit_trail.json of agent-loop activity (time, tool name, short args/result, stop reason). do not wipe it between runs. think up some safety rules to give to the agent and put them in prompts/prompt.md . finish output/harness.md so it is clear how the system works including model fields in models.py and why you chose them, tools and abilities, safety rules, and specs (loop limits, result caps, models, how to run front and back)

**Follow-up prompt (if needed):**

[Add follow-up prompt here]

## Problem 13

**Prompt:**

ok now put my code in  a folder named hw4 and push it to a new public github repository and give me the repo url. do NOT put my real .env , campus_customs.db or product images in the github repo. use .gitignore . include .env.example with palceholders only. make sure the data follows the attached expected layout. the agent itself is four files under backend/  : prompts/prompt.md , agent.py , tools.py and models.py README.md should explain how to run the front end and back end after placing the data pack. also add this prompt to the final placeolder in AI_prompts.md

**Follow-up prompt (if needed):**

[Add follow-up prompt here]