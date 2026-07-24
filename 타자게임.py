import tkinter as tk
from tkinter import messagebox
import random as r
import time

# 단어 리스트
words = ["cat", "dog", "fox", "monkey", "tiger", "mouse", "panda", "frog", "snake", "wolf", "tiger", "lion"]

class TypingGame:
    def __init__(self, root):
        self.root = root
        self.root.title("Typing Game")

        # Initialize game variables
        self.start_time = None
        self.word = r.choice(words)
        self.score = 0
        self.total_questions = 5

        # GUI Components
        self.label_instruction = tk.Label(root, text="[타자게임] 시작하려면 시작 버튼을 누르세요.", font=("Arial", 14))
        self.label_instruction.pack(pady=10)

        self.label_word = tk.Label(root, text="", font=("Arial", 18, "bold"), fg="blue")
        self.label_word.pack(pady=10)

        self.entry_answer = tk.Entry(root, font=("Arial", 14))
        self.entry_answer.pack(pady=10)
        self.entry_answer.bind("<Return>", self.check_answer)

        self.button_start = tk.Button(root, text="시작", font=("Arial", 14), command=self.start_game)
        self.button_start.pack(pady=10)

        self.label_score = tk.Label(root, text="", font=("Arial", 14))
        self.label_score.pack(pady=10)

    def start_game(self):
        self.start_time = time.time()
        self.score = 0
        self.word = r.choice(words)
        self.label_word.config(text=self.word)
        self.label_score.config(text=f"문제: 1/{self.total_questions}")
        self.entry_answer.delete(0, tk.END)
        self.entry_answer.focus()

    def check_answer(self, event):
        user_input = self.entry_answer.get()
        if user_input == self.word:
            self.score += 1
            if self.score == self.total_questions:
                end_time = time.time()
                elapsed_time = end_time - self.start_time
                messagebox.showinfo("타자 게임 종료", f"축하합니다! 총 소요 시간: {elapsed_time:.2f}초")
                self.reset_game()
                return
            else:
                self.word = r.choice(words)
                self.label_word.config(text=self.word)
                self.label_score.config(text=f"문제: {self.score + 1}/{self.total_questions}")
        else:
            messagebox.showwarning("오답", "다시 시도하세요!")

        self.entry_answer.delete(0, tk.END)
        self.entry_answer.focus()

    def reset_game(self):
        self.label_word.config(text="")
        self.label_score.config(text="")
        self.entry_answer.delete(0, tk.END)

if __name__ == "__main__":
    root = tk.Tk()
    game = TypingGame(root)
    root.mainloop()
