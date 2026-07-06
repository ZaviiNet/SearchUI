import numpy as np
import re

class LocalVectorIndex:
    def __init__(self):
        self.documents = []  # list of dict: {"id": str, "text": str}
        self.vocab = {}
        self.idf = {}
        self.tf_idf_matrix = None
        
    def _tokenize(self, text):
        words = re.findall(r'\b[a-zA-Z0-9_]+\b', text.lower())
        return words
        
    def add_documents(self, documents):
        """
        documents: list of dict {"id": str, "text": str}
        """
        self.documents.extend(documents)
        self._build_index()
        
    def _build_index(self):
        if not self.documents:
            return
            
        df = {}
        doc_tokens = []
        for doc in self.documents:
            tokens = self._tokenize(doc["text"])
            doc_tokens.append(tokens)
            unique_terms = set(tokens)
            for term in unique_terms:
                df[term] = df.get(term, 0) + 1
                
        self.vocab = {term: idx for idx, term in enumerate(sorted(df.keys()))}
        vocab_size = len(self.vocab)
        num_docs = len(self.documents)
        
        self.idf = {}
        for term, count in df.items():
            self.idf[term] = np.log((1 + num_docs) / (1 + count)) + 1
            
        self.tf_idf_matrix = np.zeros((num_docs, vocab_size))
        for doc_idx, tokens in enumerate(doc_tokens):
            tf = {}
            for token in tokens:
                tf[token] = tf.get(token, 0) + 1
            for token, tf_val in tf.items():
                if token in self.vocab:
                    col_idx = self.vocab[token]
                    self.tf_idf_matrix[doc_idx, col_idx] = tf_val * self.idf[token]
                    
        norms = np.linalg.norm(self.tf_idf_matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self.tf_idf_matrix = self.tf_idf_matrix / norms
        
    def query(self, query_text, top_k=3):
        if not self.documents or not self.vocab or self.tf_idf_matrix is None:
            return []
            
        query_tokens = self._tokenize(query_text)
        query_vector = np.zeros(len(self.vocab))
        
        tf = {}
        for token in query_tokens:
            tf[token] = tf.get(token, 0) + 1
            
        for token, tf_val in tf.items():
            if token in self.vocab:
                col_idx = self.vocab[token]
                query_vector[col_idx] = tf_val * self.idf[token]
                
        q_norm = np.linalg.norm(query_vector)
        if q_norm > 0:
            query_vector = query_vector / q_norm
            
        similarities = np.dot(self.tf_idf_matrix, query_vector)
        top_indices = np.argsort(similarities)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            score = float(similarities[idx])
            if score > 0.0:
                results.append({
                    "id": self.documents[idx]["id"],
                    "text": self.documents[idx]["text"],
                    "score": score
                })
        return results
