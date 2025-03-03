import discord
import aiohttp
import json
import requests


TOKEN = "MTM0MjMzNzU4NDg2MDIzMzc4OA.G8VkFT.kjImkQUA0ULDZeR0yr-ycl41rQpXmc7f4Da3IU"
DISCORD_API_BASE = "https://discord.com/api/v9"

admin = [1229197671839826037, 456225181107486721, 1343382498918404226, 1342337584860233788, 631688884060946432]

client = discord.Client()

INVITE_FILE = 'main/invites.txt'


@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')
    
        
@client.event
async def on_message(msg):
    if msg.channel.type is discord.ChannelType.private:
            if msg.author.id not in admin:
                await msg.channel.send(f"This command is reserved for admins.")
                return
            if msg.content.startswith('/purchase'): #invite to server
                purchase_info = msg.content.split('|')
                print(purchase_info)
                status = await try_purchase(purchase_info[4], purchase_info[2], purchase_info[5])
                print("tried to purchase")
                await msg.channel.send(f"<PAYMENT_DETAILS>|{purchase_info[1]}|{purchase_info[2]}|{purchase_info[3]}|{purchase_info[5]}|{status}")
                
            if msg.content.startswith('/plans'):
                plans = await get_sub_plans()
                await msg.channel.send(f"<PLANS>{plans}")
            if msg.content.startswith('/card'):
                await add_payment_source()

async def try_purchase(sku_id: int, plan_name: str, amount:int):
    skus = await client.fetch_sku_subscription_plans(sku_id)
    sku = next((plan for plan in skus if plan.name.lower() == plan_name.lower()), None)

    if sku is None:
        print(f"SKU with plan name {plan_name} not found.")
        return
    
    expected_amount = sku.price
    expected_currency = sku.currency

    payment_sources = await client.payment_sources()

    if not payment_sources:
        print("No payment sources found.")
        return

    payment_source = payment_sources[0]  
    new_billing_address = discord.BillingAddress(name="Nicholas Hamilton", address="710 E Sagebrush St", city="Phoenix",country="US")
    new_billing_address.state = "AZ"
    new_billing_address.postal_code = "85296"

    
    await payment_source.edit(billing_address=new_billing_address)

    print(payment_source.billing_address)
    print(payment_source.invalid)
    valid_bill = await payment_source.billing_address.validate()
    print(valid_bill)

    try:
        purchase = await sku.purchase(
            payment_source=payment_source,
            expected_amount=expected_amount,
            expected_currency=expected_currency,

        )
        print(f"Purchase successful: {purchase}")
        return True
    
    except discord.errors.DiscordServerError as e:
        print(f"Server error occurred: {e}")
        return False
    except Exception as e:
        print(f"An error occurred: {e}")
        return False


    


        

async def get_sub_plans():
    subscription_plans = await client.premium_subscription_plans()
    giftable_plans_dict = {}

    for plan in subscription_plans:

        if "nitro" in plan.name.lower(): # i was trying to sort it by only returning ones that are "giftable", but i gave up because it was being annoying. :p
            giftable_plans_dict[plan.name] = plan.sku_id  

    print(giftable_plans_dict)
    return giftable_plans_dict


async def add_payment_source():
    try:
        payment_gateway = discord.PaymentGateway.braintree

        billing_address = discord.BillingAddress(
            name="John Doe",                 # Your name (as associated with payment method)
            address="710 E Sagebrush St",    # Street address
            city="Gilbert",                  # City
            country="US",                    # Country
            state="AZ",                      # State (California)
            postal_code="85296",             # Postal code (Zip code)
            email="johndoe@example.com"      # Email associated with the billing address (optional)
        )
        print("Billing address:", billing_address)

        # Try creating the payment source
        payment_source = await client.create_payment_source(token=TOKEN, payment_gateway=payment_gateway, billing_address=billing_address)
        print("Payment source added successfully:", payment_source)

    except discord.errors.CaptchaRequired as exception:
        # Handle the CAPTCHA challenge if it's raised
        print("CAPTCHA required, attempting to solve...")
        solution = await discord.Client.handle_captcha(exception)  # Call the CAPTCHA handler
        print("CAPTCHA solved:", solution)
        
        # After solving the CAPTCHA, try again
        payment_source = await client.create_payment_source(token=TOKEN, payment_gateway=payment_gateway, billing_address=billing_address)
        print("Payment source added successfully after CAPTCHA:", payment_source)
    
    except Exception as e:
        print("An error occurred:", e)

        


client.run(TOKEN)