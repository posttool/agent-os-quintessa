# Agent OS - Quintessa #




# Primary control loop #


Before any UI thinking, establish an AgentReasoningLoop class. The agent reasoning loop takes a chain-of-thought approach where there is a core set of capabilities and evaluates which ones it needs to execute one at a time. The core set of capabilities should be configurable. Each capability is expressed as a simple md file. The initial set of reasoning capabilities are: memory reading, writing and organizing; tool discovery and tool use; and generating user interfaces. A reasoning session is triggered by any kind of input, such as text or speech input, incoming messages, location changes or vision events from a camera. Reasoning might begin with the choice of a capability, such as deciding whether the incoming data should be added to memory, using generative ux to get more facts from the user. Each reasoning step picks a next reasoning step to execute or is determined to be the end of the chain. At each step, context should be aggregated within the session memory for traces. There can be many control loops running simultaneously all reading and writing from the same shared memory space. The control loops should be resilient to LLM failures, resting as needed or falling back to older models. When we talk about memory we mean any active reasoning process as well as any facts derived from the process,


Do not use any traditional string parsing, regular expression or static text to reason. The agent LLM based reasoning chain should do all the main computing. 


Make sure that dataclasses each have their own file instead of putting everything in one file. The separation between the agent memory and any particular design system should be clean. The agent reasoning and memory should be available on any device.


If there are sample data structures for helping the user bootstrap an environment such as tool suggestions or ambient data suggestions, put that data in separate files as well. Use the aura persona tool to create materials for samples and tests.


Make the backend in Python.






# Description of initial agent capabilities #


## Memory ##
The events are organized into topics. Instead of topics full of raw event logs, the topics are structured in terms of their lifecycle and sub topics. The raw events are available for auditing purposes, but not central to the topic based organizing. Use an LLM to help merge new incoming information with the existing graph and really try to understand when nodes or relationships are out of date and should be deleted. The memory system might know their favorite foods or allergies or family, as well as routines.
  * Node types: personal preference, project context, ambient state, tool knowledge, active process, document
  * Edge types: relates to, executing for, …


This is also the time for the agent to retrieve data that might be important for it to know when helping to support the task. This could be preferences for dinner (food, location, app to use), if the user asked about ordering dinner or it could be how old his child is, if he wants to buy a birthday present for him.


Memory is also full of “documents”. These are progressively built memories nested within a single root that aggregate the lifecycle of a project.


## Documents ##
At first, new documents might be made for basic topics with little information attached. As the user builds a memory, these cards become aggregates of our history within the topic as well as a surface to display new activity or work in progress. 


At any time, a user may have a way to recall these documents or it might be useful to recall a document when it is relevant, such as a flight change that will impact other aspects of a trip.  


The documents are somewhat mapped to a UX experience in that they grow as the user interacts with them. When actions are updated and suggested within a document, the document should contain realtime status of the process, and the results when complete as well as follow up actions. Each document tracks progress toward completion of the topic. This means that when a process is started and as actions are taken or completed by the agent or user, that the document is archived. Examples are dinner delivery, or planning and taking a trip, or tracking homework for the fall semester, or building an ADU in the backyard. Each goes through a lifecycle and its state and progress is tracked within the document.


The Index / Graph of Topics or “Cards”
Information is clustered around user topics (or cards in Nadav’s drawing). The topics should have enough meta data attached that the agent can reason about how to navigate, display and maintain (add, remove, regroup) the index. The index is a highly organized view of the user’s world.


We will want something that can be centralized so that the personal wiki is available from any surface, and eventually the wiki might appear on your Chrome New Tab page or be available through glasses.
Index example
The content categories of the index should be flexible - a user (or agent) should be able to add a new category at any time. The following is a sample of how we might organize topics for a college student. 


Examples:


Academics
History essay
History test prep
Math test prep
Dinner Plans  
Pick a place
Party Planning
Birthday gift
Location selection
New Sofa
Online browsing session
Thoughts from Sofia
Health
Sleep log
Step goal accomplished
To dos
Grocery list
Submit paperwork
Weather


Adding to and updating the index
As new information is ingested by the signal aggregation phase, it might be added to the index. At this point (differing slightly from the architecture), its importance is not judged for display but rather the following bits of meta data are computed or attached to the parent “topic”. It seems reasonable at least in writing this, to separate maintaining the index / wiki from the action of reducing it to the most salient, contextual bits.


Index meta data
If the index of topics can be saved with meta data, that makes it easy to display in context with reliability and controllability. 
Trigger types & trigger reasoning
User triggering overrides
Summary of topic & summary of new observations
Progress
Meta data - Trigger types & defaults
While we imagine users will want a lot of control here, it's desirable for the agent to reason about “default” contextual appropriateness when it creates or updates a topic or subtopic.  The trigger types are:
By time
By (semantic) location
By activity
By observation e.g. all the above as well as incoming message, screen observation, intent trigger, etc etc. We can start with time, location and activity.
Also important are concepts like
Before, after, during
Near, far, leaving, arriving
When I reach, If I dont 
When X arrives


Example reasoning:


Academics [Show mornings, at school, highlight test or assignment due dates]
Dinner Plans  [Day before, day of]
New Sofa [Show at home]
Party Planning [Home]
Health [After workout/exercise]
To dos
Grocery [At grocery store]
Submit paperwork [Unknown]
Weather [Morning]
Meta data - Trigger user preferences
Users can set the importance and the context of the importance. Example user overrides:


Academics [Top priority, show 7am-midnight M-F]
To dos
Grocery list [Before leaving work, At store]
Submit paperwork [when receipt received]


We need to think about the UX here. For example, when I swipe “academics” away, can the agent (discretely)  ask “why?” user says “never on the weekend”
Meta data - “Summary” / Last seen
When new info comes in, the agent needs to communicate if there is new content in a wiki entry since I last saw the card. For example, if I haven’t checked my phone in an hour and a new message about picking a place has arrived, the “Dinner Plans” summary will have been updated, and signified as “new”. If a topic has a lot of new info, it might be used to prioritize what is displayed.


Academics [New info: Test date changed]
History essay
History test prep [New due date 5/27/26]
Math test prep
Dinner Plans  [New info: Jane wants to go to Zuni]
Pick a place [WhatsApp Jane: …]
Reservation [OpenTable callback]
Party Planning [New info: Dara says you can use her place, Heiko has a gift idea]
Birthday gift [WhatsApp Heiko: …]
Location selection [Gmail Darla: …]
To dos
Grocery list  [Item added from text msg]
Meta data - Progress
It might be that when a user has time and nothing urgent that their agent would deliver content that could be progressed, e.g. that sofa that you haven't bought, even though you keep going back to the site to look at it. Need more research? Waiting for a deal? What’s up?


Displaying topics
At any given time, the agent can reduce the index to the topics / cards that are contextually relevant.  Users might want to browse or search all the topics… but mostly we hope our agent can manage the display with context.


Examples: 
When I am at the grocery store, the shopping list appears. It has been compiled by the personal knowledge graph from ambient signals so that it was ready without me having to make it. 
Days before the test, help me practice.
Days before the party, help me with the gift and the location. As details are confirmed, help communicate with the guests. The day before, remind guests. On the day of, prioritize their communication, automate responses for location or time requests.
Three days before the dinner party, help me book the reservation. The day before, remind me. The day of, help me get there.
Old entries
The wiki should probably be pruned.


When a date has passed, for example, a dinner party, then the information probably shouldn’t be displayed any more, unless you still owe someone money for it… or we want to give folks a chance to archive? Transform? File away? Email to someone?


If a topic hasn't been updated in a while and has no due date, it might be surfaced “still relevant?”


Does this mean the entry is deleted? Maybe. 
Personal Documents
Finally, some notes about the pages themselves. These pages would need to be maintained if the user wants to dive into a topic or if the LLM needs to record an observation or new artifact. For example the “math test prep” entry might contain info as follows as a structured record.


Title: Math test prep


Description: User wants to get proficiency on the topics for the upcoming quiz.


Topic: Algebra 4
Equations and inequalities
Graphing
Substitution
Elimination


Progress overview: 
Proficiency with equations and inequalities <complete>
Graphing <not started>
Substitution <needs attention>
Elimination <not started>


Sections:


Section:
Title: Equations and inequalities
Overview: …
Details: {}
Actions taken: Practiced in Quiznet App achieving a score of X


Section:
Title: Graphing
…


Section: 
Title: Substitution
…
Actions: <custom app creation complete, click to try>


Section: 
Title: Graphing
…


Links to useful apps/sites/services/other documents or sections: 
Link
Link
Link


Key dates: 
5/26/2026 - Assignment 4 due
5/29/2026 4pm - Test in testing center 4A


Relevant observations:
Message from Jerry: Did you finish the homework?
Message from Dr. Song: Chapter 6 downloads
Sites viewed: X, Y, Z
Important calendar notes
My agent knows my calendar, whether I use one or not


Whether the user uses the calendar tool or not, the agent should. As tentative dates come in the agent should present them as “penciled in” for the user to approve. The agent should always know not just where the user is, but where they will be. This allows the agent to spot conflicts and surface them. This might be one of the most important tools that the agent uses outside of the personal wiki. If we dont have access easily to a calendar, the agent might maintain its own calendar data.


Dinner Plans  [New info: Jane wants to go on Tuesday; Conflicts with history test prep]
Picking a time and place [WhatsApp Jane: …]
Due dates
Topics are sometimes (often) date bound. It seems reasonable that the index would have some high level info available for agent reasoning with regards to when/how to surface information. Automatically extracting due dates will help us know when and how to surface them. This information can be derived from input signals or user control.


Examples:


Academics [Essay due tomorrow]
History essay [Due 6/12/2026]
History test prep [Before 6/26/2026]
Math test prep [In class 6/14/2026]
Dinner Plans  [Next week]
Party Planning [6/29/2026]
New Sofa [Unset→Before Mom arrives]
Actions
Now that all this organization mechanics are in place, let's help users!!!!


One of the biggest problems users face with agents is that they dont know what they can do. With a rich personal KG, there are many opportunities to suggest help in context to the user.  Ultimately this becomes an interface where the signal combining agent / personal wiki manager can ask the orchestrator: given this context, what help is available? 


Examples:


Sofa - view in living room, compare prices, look for similar but less expensive options, etc.
Travel - help book tickets, research things to do, make a walking tour for me today, etc
Event - get gifts, book location, communicate with folks attending, etc
Academic - generate flash cards, quizzes, tutorials etc


## UX Disambiguation ##
If the agent thinks it might be helpful to ask the user to help clarify something before it commits something to memory or assembles tools to help with a task, it should ask with a user interface. Ask the question before going to another step. This disambiguation should also occur when the agent has to make a choice that it is not sure about like picking between two colors with no memory of color preference or being about to spend money. When generating UI for disambiguation or any other purpose, make sure to pass UI feedback back to the agentic loop that is waiting, passing the current UI or document context and the values collected in forms as well as the values selected back. The UI feedback should be a continuation of the context that triggered it. When the disambiguation step happens, the agent loop should pause until it gets info from the UX. 


Disambiguation can handle tool calling boundaries such as whether to spend money. In situations where the tool requires some explicit information or permission, make sure that the permission is passed across the chain and persisted in a way that might be used for future reasoning. Don’t forget that the user already approved a spend in a tool call that comes later in a reasoning chain.


When the ux_disambiguation is answered close any form in the space and return to the context, a document section, with confirmation of the user data as well as information about the continued progress steps. if there is new ux_dismabiguation in the steps, handle that the usual way, returning back again reporting the results of the reasoning chain until it is complete at which time the document over and the target section can be rerendered if the results document and section has changed.




## Tool discovery ##
Once it has been organized, contextualized and retrieved or saved, the agent must now gather tools that can help with the current topic and situation.


The only default tools are web access and device control:
  * Web access includes Google search and being able to download files to the device. 
  * Device control specifically relates to the experience screen and how the agent uses the device surfaces to communicate effectively with the user. 


If the agent doesn't have any tools to help solve a problem and believes that it could search for tools to install or even code its own tool for the situation it will.  A tool often contains a set of functions, such as [read and write], or [add to cart, remove from cart, checkout]. A tool is defined as a list of function signatures with typed parameters and return values.  Tools are aware of permission or decision boundaries that need user oversight. Each function within the tool should have different levels of oversight, starting with ok to automatically fill from memory, to always ask the user about it.


## Tool use ##
When the agent has assembled, discovered or recalled a tool it will use it.  The use of a tool doesn't need to complete the entire action and can simply be a step toward completion. Often when using a tool it makes sense to surface some of its options near the context (for example canceling a ride after ordering it). The agent will keep trying to surface tools and data that can move the document or topic along. Tools are a group of functions paired with preferences about use gates such as whether the agent can perform it autonomously or whether it should check with the user (disambiguate).


If a tool kicks off a process in the real world, or in an app, it will subscribe to progress from that event or app so that it can report progress, as well as if there are snags that require disambiguation or if the process is complete.


## Device tool details ##
It is an LLM based tool that can reason about the device it is inhabiting, with access to all of its surfaces and screens (read and write) as well as access to its sensors. It is able to reason about how to best update the experience surfaces given the state of memory in conjunction with the main reasoning loops. It will send UX changes back to the main agent loop with the context that presented the original UX so that the results can be returned to that context. 






# Make these data structures and tests first-- the Web App UI specification comes next. #




# Web App Screens #


This is a tool that ultimately lets us refine an experience. It leverages the main agent reasoning loop as its primary computing mechanism. The tool should have a very modern and minimalistic aesthetic as it is meant to focus on the experience which is a next generation mobile device experience. 


The web application tool shows a main Experience panel with 4 supporting side panels:


Memory
Tools 
Data
Traces


The main interface should have a button to clear the memory which should also clear the dashboard. Start with nothing in memory, traces or dashboard. Don’t create any sample data whatsoever. Just start with a blank slate. 


The main interface should offer a way to switch between dark and light mode.


The main interface should offer a way to control which version of Gemini is used (3.8 flash by default) as well as the resting and fallback strategy.


The main interface should offer a way to pick a default user from the Aura persona simulation, which clears memory and tools and data subscriptions, then starts to walk through a day in the life of the persona via data emissions. The simulation can be stopped and cleared with the “clear memory” button.




## Memory ##
This screen is a complete view into the agent’s memory. The memory system is a graph and one of the agent's primary tools. The memory is graph based and represents knowledge about the user in the context of their world, needs, and actions. 


## Tools ##
All tools (besides built in) will be created on demand. Initially tools can be discovered with the web search tool. When a tool is created on demand, it might be based on a web API or MCP interface. A differently grounded LLM can also be a tool. Finally, the agent might decide to write code for the tool. This screen allows us to create, manage and delete tools. If the agent uses a tool that has a long running response, like ordering a taxi or some product to be built or delivered, the agent should also subscribe to an ambient data stream that monitors the progress of the activity.


## Data ##
The data screen allows us to subscribe to or simulate events that come from streaming or subscription type services. There are no ambient data sources set by default, but there are templates for creating incoming emails and sms (with Aura persona grounding), as well as home security streams, a drive from home to the office, changing location events etc. Users can also vibe code new ambient data sources. The ambient data screen should have global on/off controls as well as speed controls to control the rate of emission (per source). Global emission should be on by default but with no default streams. The tool using part of the system might create ambient data subscriptions to manage the lifecycle of a long running process. The ambient data should emit events in a simulation, so as the event virtually progresses the agent loop will receive the progress events. When the event is complete, the subscription should be deleted or archived. 


## Traces ##


Available to see a complete log of agentic reasoning indexed by trigger. Every step of the process can be viewed here in detail.




# Experience #
The main experience panel (persistent across the entire app) shows us what a completely integrated consumer experience looks like. The device is one of the agents' primary tools. Its style sheet and visual display should be isolated from the surrounding web app, and replaceable as a skin.


## Main Experience concepts ##
### Dynamic Island ###
This is a small island always at the top of the phone screen. It has a pulsing, glowing dot when there is agent activity/reasoning. It also has 1 or two words about what the agent is doing. It gets very small when nothing is happening.
### Contextual Brief ###
The contextual brief shows the most important items from the memory and agent reasoning. It should prioritize surfacing details from memory that are contextually relevant to time & place (like a grocery list at the grocery store or a qr code at a venue), or high priority (communication that it urgent, or changes in an upcoming event), or actions that the user needs to take (high priority disambiguation). It should always be very glancable with call to action rather than complete details or choices presented inline. It is expects that when a user taps on an indicator in the contextual brief that they will be taken to the intent space to do more.
### Intent Space ###
These are the persistent documents that help the user get things done in the context of a document, project or goal.




## Main Experience screens ##
### Lock screen ###
The lock screen shows the time and date (large), as well as the dynamic island and contextual brief. The user must unlock the phone to get to the following three screens which are arranged from left to right as “Discover”, “Home”, “Spaces”
### Home screen ###
The home screen shows the dynamic island, the contextual brief, the apps/tools, and a multimodal input bar that sends commands to the agent.
### Intent screen, “Spaces” ###
This is the main workspace or canvas for the agent user interface. It should show all the currently active projects as buttons or tabs, and it is expected that the content on this screen is constantly changing based on memory and user need. This is where disambiguations will occur or where documents will be displayed to help the user get things done. The agent will bring documents or disambiguations here as needed or the user can ask for them by topic.
### Discovery screen ###
The agent will also periodically populate the discovery screen with topics that are related to the users interest or projects but that were not asked for directly. 