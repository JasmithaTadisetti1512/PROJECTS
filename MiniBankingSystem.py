import json
import os

# File to store user data
USER_FILE = "users.json"

# Load user data from file
def load_users():
    if not os.path.exists(USER_FILE):
        return {}
    with open(USER_FILE, "r") as file:
        return json.load(file)

# Save user data to file
def save_users(users):
    with open(USER_FILE, "w") as file:
        json.dump(users, file)

# Register a new user
def register(users):
    username = input("Enter a new username: ")
    if username in users:
        print("Username already exists.")
        return
    pin = input("Set a 4-digit PIN: ")
    users[username] = {"pin": pin, "balance": 0}
    save_users(users)
    print("Registration successful!")

# Login existing user
def login(users):
    username = input("Enter your username: ")
    pin = input("Enter your PIN: ")
    user = users.get(username)
    if user and user["pin"] == pin:
        print(f"Welcome, {username}!")
        banking_menu(users, username)
    else:
        print("Invalid username or PIN.")

# Banking operations
def banking_menu(users, username):
    while True:
        print("\n--- Banking Menu ---")
        print("1. Check Balance")
        print("2. Deposit")
        print("3. Withdraw")
        print("4. Logout")

        choice = input("Select an option: ")

        if choice == "1":
            print(f"Your balance is: ₹{users[username]['balance']}")
        elif choice == "2":
            amount = float(input("Enter amount to deposit: "))
            users[username]['balance'] += amount
            save_users(users)
            print("Amount deposited successfully.")
        elif choice == "3":
            amount = float(input("Enter amount to withdraw: "))
            if amount <= users[username]['balance']:
                users[username]['balance'] -= amount
                save_users(users)
                print("Amount withdrawn successfully.")
            else:
                print("Insufficient balance.")
        elif choice == "4":
            print("Logging out...")
            break
        else:
            print("Invalid option.")

# Main program loop
def main():
    users = load_users()
    while True:
        print("\n--- Welcome to Python Bank ---")
        print("1. Register")
        print("2. Login")
        print("3. Exit")

        option = input("Select an option: ")

        if option == "1":
            register(users)
        elif option == "2":
            login(users)
        elif option == "3":
            print("Thanks for using Python Bank!")
            break
        else:
            print("Invalid selection. Try again.")

if __name__== "__main__":
    main()