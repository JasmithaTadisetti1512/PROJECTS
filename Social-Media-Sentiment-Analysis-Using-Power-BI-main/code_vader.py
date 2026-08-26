import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import nltk
from nltk.sentiment import SentimentIntensityAnalyzer
from wordcloud import WordCloud
import re
import string

# Download necessary NLTK data
nltk.download('vader_lexicon')

# ✅ Load your dataset (uploaded file path)
df = pd.read_csv(r"C:\Users\surap\Desktop\Social-Media-Sentiment-Analysis-Using-Power-BI-main\sentimentdataset.csv")

# ✅ Inspect to confirm column names
print("Available columns:", df.columns)

# ✅ Rename or identify the correct text column
# If your dataset has 'Tweet', 'Post', or another column instead of 'text', update it
text_col = None
for col in df.columns:
    if 'text' in col.lower():
        text_col = col
        break

if not text_col:
    raise ValueError("No text column found. Please make sure your dataset has a text column like 'text' or 'Tweet'.")

# ✅ Clean the text
def clean_text(text):
    text = str(text).lower()
    text = re.sub(r"http\S+|www\S+|https\S+", '', text, flags=re.MULTILINE)
    text = re.sub(r'\@\w+|\#\w+', '', text)  # fixed regex to match @ and # tags properly
    text = text.translate(str.maketrans('', '', string.punctuation))
    return text

df['cleaned_text'] = df[text_col].apply(clean_text)

# ✅ Sentiment analysis using VADER
sia = SentimentIntensityAnalyzer()

def get_sentiment(text):
    score = sia.polarity_scores(text)
    compound = score['compound']
    if compound >= 0.05:
        return 'Positive'
    elif compound <= -0.05:
        return 'Negative'
    else:
        return 'Neutral'

df['Sentiment'] = df['cleaned_text'].apply(get_sentiment)

# ✅ Generate WordClouds
for sentiment in ['Positive', 'Negative', 'Neutral']:
    text_data = ' '.join(df[df['Sentiment'] == sentiment]['cleaned_text'])
    if text_data.strip():  # Check if there's text to show
        wc = WordCloud(width=800, height=400, background_color='white').generate(text_data)
        plt.figure(figsize=(10, 5))
        plt.imshow(wc, interpolation='bilinear')
        plt.axis('off')
        plt.title(f'Word Cloud for {sentiment} Sentiment')
        plt.show()
    else:
        print(f"No {sentiment} sentiment data available to generate word cloud.")

# ✅ Save cleaned and analyzed output for Power BI
output_path = r"C:\Users\surap\Desktop\Social-Media-Sentiment-Analysis-Using-Power-BI-main\sentimentdataset.csv"
df.to_csv(output_path, index=False)

print(f"\n✅ Sentiment analysis results saved to: {output_path}")
