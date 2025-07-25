from fastapi import APIRouter, HTTPException, Depends, Query, Request
from typing import List
from datetime import datetime
from models.words_model import WordCreate, WordResponse, WordUpdate, DialogueMessage, DialogueResponse
from utils.firebase_auth import get_current_user_firebase
from models.user import User
from db.words import (
    get_user_words, create_word, update_word, 
    delete_word, get_known_words
)
from services.dialogue_service import run_dialogue_turn
from services.words_service import suggest_new_words_for_user

router = APIRouter(tags=["words"])

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    from datetime import datetime
    return {"status": "healthy", "timestamp": datetime.now()}



@router.get("/words/{user_id}", response_model=List[WordResponse])
async def get_user_words_endpoint(user_id: str, current_user: User = Depends(get_current_user_firebase)):
    """Get all words for a user"""
    # Verify the user is requesting their own data
    if current_user.user_id != user_id:
        raise HTTPException(status_code=403, detail="Can only access your own words")
    
    try:
        words = get_user_words(user_id)
        return words
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch words: {str(e)}")

@router.post("/words", response_model=WordResponse)
async def create_word_endpoint(word: WordCreate, current_user: User = Depends(get_current_user_firebase)):
    """Add a new word for a user"""
    # Verify the user is creating words for themselves
    if current_user.user_id != word.user_id:
        raise HTTPException(status_code=403, detail="Can only create words for yourself")
    
    try:
        new_word = create_word(word.user_id, word)
        return new_word
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create word: {str(e)}")

@router.put("/words/{word_id}", response_model=WordResponse)
async def update_word_endpoint(word_id: str, updates: WordUpdate, current_user: User = Depends(get_current_user_firebase)):
    """Update a word"""
    try:
        updated_word = update_word(word_id, updates)
        if not updated_word:
            raise HTTPException(status_code=404, detail="Word not found")
        
        # Verify the user owns this word
        if updated_word.user_id != current_user.user_id:
            raise HTTPException(status_code=403, detail="Can only update your own words")
        
        return updated_word
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update word: {str(e)}")



@router.delete("/words/{word_id}")
async def delete_word_endpoint(word_id: str, current_user: User = Depends(get_current_user_firebase)):
    """Delete a word"""
    try:
        # First get the word to check ownership
        words = get_user_words(current_user.user_id)
        word_to_delete = next((w for w in words if w.id == word_id), None)
        
        if not word_to_delete:
            raise HTTPException(status_code=404, detail="Word not found")
        
        success = delete_word(word_id)
        if not success:
            raise HTTPException(status_code=404, detail="Word not found")
        
        return {"message": "Word deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete word: {str(e)}")

@router.post("/dialogue", response_model=DialogueResponse)
async def chat_with_ai(message: DialogueMessage, current_user: User = Depends(get_current_user_firebase)):
    """Send message to AI tutor"""
    # Verify the user is sending messages for themselves
    if current_user.user_id != message.user_id:
        raise HTTPException(status_code=403, detail="Can only send messages for yourself")
    
    try:
        # Get AI response using existing dialogue service
        ai_response = await run_dialogue_turn(
            user_id=message.user_id,
            student_response=message.message
        )
        
        # Get suggested words for this user
        try:
            word_suggestion = suggest_new_words_for_user(message.user_id)
            suggested_words = word_suggestion.new_words
        except Exception:
            # Fallback if word suggestion fails
            suggested_words = []
        
        return DialogueResponse(
            response=ai_response,
            suggested_words=suggested_words
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process message: {str(e)}") 

@router.get("/new-words/{user_id}", response_model=List[WordResponse])
async def get_new_words_endpoint(user_id: str, current_user: User = Depends(get_current_user_firebase)):
    """Get all new words for a user using suggest_new_words_for_user"""
    if current_user.user_id != user_id:
        raise HTTPException(status_code=403, detail="Can only access your own new words")
    try:
        # Call suggest_new_words_for_user (now async)
        word_suggestion = await suggest_new_words_for_user(user_id)
        
        if word_suggestion and hasattr(word_suggestion, "new_words"):
            # Convert WordSuggestion to WordResponse objects
            new_word_objs = []
            for word in word_suggestion.new_words:
                usage = word_suggestion.usages.get(word)
                if usage:
                    # Create WordResponse object from the suggestion data
                    # Note: These are suggested words, not yet in known_words table
                    word_response = WordResponse(
                        id=f"new_{word}",  # Generate a temporary ID for new words
                        user_id=user_id,
                        word=word,
                        translation=usage.translation,  # Use the word translation
                        example=usage.fr,  # Use French sentence as example
                        created_at=datetime.now()
                    )
                    new_word_objs.append(word_response)
            return new_word_objs
        else:
            return []
    except Exception as e:
        import traceback
        print(f"Error in get_new_words_endpoint: {str(e)}")
        print("Full stack trace:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to fetch new words: {str(e)}") 