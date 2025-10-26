import logging

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    RoomInputOptions,
    WorkerOptions,
    cli,
    metrics,
    function_tool,
    RunContext,
)
import httpx
import uuid
import asyncio
from livekit.plugins import noise_cancellation, silero

logger = logging.getLogger("agent")


import os


import logging





from dotenv import load_dotenv


from livekit.agents import (


    Agent,


    AgentSession,


    JobContext,


    JobProcess,


    MetricsCollectedEvent,


    RoomInputOptions,


    WorkerOptions,


    cli,


    metrics,


    function_tool,


    RunContext,


)


import httpx


import uuid


import asyncio


from livekit.plugins import noise_cancellation, silero





logger = logging.getLogger("agent")








load_dotenv(".env.example")





BACKEND_URL =  "http://localhost:8000"








class Assistant(Agent):


    def __init__(self, instructions: str, knowledge_base_entries: list) -> None:


        super().__init__(


            instructions=instructions,


        )


        self.knowledge_base_entries = knowledge_base_entries





    @function_tool


    async def ask_human_expert(self, context: RunContext, question_text: str):


        """


        Use this tool when you do not know the answer to a question.


        It will escalate the question to a human expert and wait for their answer.


        """


        # First, check the knowledge base


        for entry in self.knowledge_base_entries:


            if entry['question_text'].lower() == question_text.lower():


                logger.info(f"Answering from knowledge base: {question_text}")


                return entry['answer_text']





        logger.info(f"Escalating question to human expert: {question_text}")


        


        question_id = str(uuid.uuid4())


        


        async with httpx.AsyncClient() as client:


            try:


                response = await client.post(


                    f"{BACKEND_URL}/questions",


                    json={"question_id": question_id, "question_text": question_text},


                )


                response.raise_for_status()


            except httpx.RequestError as e:


                logger.error(f"Error escalating question: {e}")


                return "I'm sorry, I'm having trouble connecting to my supervisor right now. Please try again later."





        # Poll for the answer with a timeout


        timeout_time = asyncio.get_event_loop().time() + 20  # 20 seconds from now


        while True:


            if asyncio.get_event_loop().time() > timeout_time:


                logger.warning(f"Timeout waiting for human expert response for question {question_id}")


                # Update status to unresolved in Firebase


                try:


                    async with httpx.AsyncClient() as client:


                        await client.put(


                            f"{BACKEND_URL}/questions/{question_id}",


                            json={"status": "unresolved"},


                        )


                except httpx.RequestError as e:


                    logger.error(f"Error updating question status to unresolved: {e}")


                return "I'm sorry, the supervisor is not available at the moment. Please try again later."





            try:


                async with httpx.AsyncClient() as client:


                    response = await client.get(f"{BACKEND_URL}/questions/{question_id}")


                    response.raise_for_status()


                    data = response.json()


                    


                    if data.get("status") == "answered":


                        answer = data.get("answer_text", "I'm sorry, I couldn't get an answer from my supervisor.")


                        logger.info(f"Received answer from human expert: {answer}")


                        return answer


            except httpx.RequestError as e:


                logger.error(f"Error polling for answer: {e}")


                # Wait a bit before retrying


                await asyncio.sleep(3)


                continue # retry


            


            await asyncio.sleep(3)








def prewarm(proc: JobProcess):


    proc.userdata["vad"] = silero.VAD.load()








async def entrypoint(ctx: JobContext):


    # Logging setup


    # Add any other context you want in all log entries here


    ctx.log_context_fields = {


        "room": ctx.room.name,


    }





    # Fetch learned answers from the API


    knowledge_base_entries = []


    async with httpx.AsyncClient() as client:


        try:


            response = await client.get(f"{BACKEND_URL}/knowledge-base")


            response.raise_for_status()


            knowledge_base_entries = response.json().get("knowledge_base", [])


        except httpx.RequestError as e:


            logger.error(f"Error fetching knowledge base: {e}")





    # Format the learned knowledge


    knowledge_string = ""


    if knowledge_base_entries:


        knowledge_string = "\nYou also know the following from your knowledge base:\n"


        for item in knowledge_base_entries:


            knowledge_string += f"- Q: {item['question_text']} A: {item['answer_text']}\n"





    # The user's base instructions


    base_instructions = """You are a helpful AI receptionist for 'TheClipJoy Salon'.


                        You are polite and professional.


                        You MUST follow these rules:


                        1. You know the salon's hours: Tuesday-Sunday, 9 AM to 6 PM.


                        2. You know the salon's location: 123 Main St.


                        3. You know what services are offered: haircuts, coloring, and styling.


                        4. You DO NOT know any pricing.


                        5. If you are asked about anything you know (hours, location, services),


                        answer it.


                        6. If you are asked about pricing or anything else you DON'T know, respond with this exact phrase: 


                        'Let me check with my supervisor and get back to you.' and next you MUST use the `ask_human_expert` tool to get the answer."""





    # Combine the base instructions with the learned knowledge


    full_instructions = base_instructions + knowledge_string





    # Create the agent with the dynamic instructions


    agent = Assistant(instructions=full_instructions, knowledge_base_entries=knowledge_base_entries)





    # Set up a voice AI pipeline using OpenAI, Cartesia, AssemblyAI, and the LiveKit turn detector


    session = AgentSession(


        # Speech-to-text (STT) is your agent's ears, turning the user's speech into text that the LLM can understand


        # See all available models at https://docs.livekit.io/agents/models/stt/


        stt="assemblyai/universal-streaming:en",


        # A Large Language Model (LLM) is your agent's brain, processing user input and generating a response


        # See all available models at https://docs.livekit.io/agents/models/llm/


        llm="openai/gpt-4.1-mini",


        # Text-to-speech (TTS) is your agent's voice, turning the LLM's text into speech that the user can hear


        # See all available models as well as voice selections at https://docs.livekit.io/agents/models/tts/


        tts="cartesia/sonic-2:9626c31c-bec5-4cca-baa8-f8ba9e84c8bc",


        # VAD and turn detection are used to determine when the user is speaking and when the agent should respond


        # See more at https://docs.livekit.io/agents/build/turns


        vad=ctx.proc.userdata["vad"],


        # allow the LLM to generate a response while waiting for the end of turn


        # See more at https://docs.livekit.io/agents/build/audio/#preemptive-generation


        preemptive_generation=True,


    )





    # To use a realtime model instead of a voice pipeline, use the following session setup instead.


    # (Note: This is for the OpenAI Realtime API. For other providers, see https://docs.livekit.io/agents/models/realtime/))


    # 1. Install livekit-agents[openai]


    # 2. Set OPENAI_API_KEY in .env.local


    # 3. Add `from livekit.plugins import openai` to the top of this file


    # 4. Use the following session setup instead of the version above


    # session = AgentSession(


    #     llm=openai.realtime.RealtimeModel(voice="marin")


    # )





    # Metrics collection, to measure pipeline performance


    # For more information, see https://docs.livekit.io/agents/build/metrics/


    usage_collector = metrics.UsageCollector()





    @session.on("metrics_collected")


    def _on_metrics_collected(ev: MetricsCollectedEvent):


        metrics.log_metrics(ev.metrics)


        usage_collector.collect(ev.metrics)





    async def log_usage():


        summary = usage_collector.get_summary()


        logger.info(f"Usage: {summary}")





    ctx.add_shutdown_callback(log_usage)





    # # Add a virtual avatar to the session, if desired


    # # For other providers, see https://docs.livekit.io/agents/models/avatar/


    # avatar = hedra.AvatarSession(


    #   avatar_id="...",  # See https://docs.livekit.io/agents/models/avatar/plugins/hedra


    # )


    # # Start the avatar and wait for it to join


    # await avatar.start(session, room=ctx.room)





    # Start the session, which initializes the voice pipeline and warms up the models


    await session.start(


        agent=agent,


        room=ctx.room,


        room_input_options=RoomInputOptions(


            # For telephony applications, use `BVCTelephony` for best results


            noise_cancellation=noise_cancellation.BVC(),


        ),


    )





    # Join the room and connect to the user


    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
            agent_name="my-receptionist-agent"  
        )
    )
