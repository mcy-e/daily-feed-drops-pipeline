from PIL import Image
Image.new('RGB', (100,100)).save('test.jpg')
from scripts.render.image_card_renderer import render_image_card
render_image_card('test.jpg', 'This is a dark fact about something creepy and dark that you did not know.', 'dark_facts', 'test_out.png')
print('Success')
