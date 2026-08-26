import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from wordcloud import WordCloud
import re
import string
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from scipy.special import softmax
import torch

# ✅ Load your dataset (uploaded file path)
df = pd.read_csv(r"C:\Users\surap\Desktop\Social-Media-Sentiment-Analysis-Using-Power-BI-main\sentimentdataset.csv")

# ✅ Inspect to confirm column names
print("Available columns:", df.columns)

# ✅ Identify the text column
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
    text = re.sub(r'\@\w+|\#\w+', '', text)  # Remove @ and # tags
    text = text.translate(str.maketrans('', '', string.punctuation))
    return text

df['cleaned_text'] = df[text_col].apply(clean_text)

# ✅ Load Twitter-RoBERTa model and tokenizer
model_name = "cardiffnlp/twitter-roberta-base-sentiment"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSequenceClassification.from_pretrained(model_name)

# ✅ Sentiment prediction function
def get_sentiment_roberta(text):
    try:
        encoded_input = tokenizer(text, return_tensors='pt', truncation=True, max_length=512)
        output = model(**encoded_input)
        scores = softmax(output.logits.detach().numpy()[0])
        sentiment_labels = ['Negative', 'Neutral', 'Positive']
        return sentiment_labels[scores.argmax()]
    except Exception as e:
        print(f"Error processing text: {text}\n{e}")
        return 'Neutral'

# ✅ Apply sentiment analysis
df['Sentiment'] = df['cleaned_text'].apply(get_sentiment_roberta)

# ✅ Generate WordClouds
for sentiment in ['Positive', 'Negative', 'Neutral']:
    text_data = ' '.join(df[df['Sentiment'] == sentiment]['cleaned_text'])
    if text_data.strip():
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
