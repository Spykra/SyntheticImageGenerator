import os
import torch
import time
import torch.optim as optim
from torchvision import datasets
from torch.utils.data import DataLoader
from convolutional_GAN_model import Generator, Discriminator
from utils import get_transform, save_generated_images, save_checkpoint, load_checkpoint

# Define the device
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Hyperparameters
lr = 0.0001
batch_size = 32
epochs = 50
noise_vector_size = 100
image_channels = 3
image_size = 256 * 256 * 3  # For 256x256 RGB images
lambda_gp = 10  # Gradient penalty lambda hyperparameter
n_critic = 5  # The number of discriminator updates per generator update

# Initialize models and move them to the correct device
generator = Generator(noise_vector_size).to(device)  # Assuming the Generator class now only needs the noise size
discriminator = Discriminator().to(device)

# Optimizers
g_optimizer = optim.Adam(generator.parameters(), lr=lr, betas=(0.5, 0.9))
d_optimizer = optim.Adam(discriminator.parameters(), lr=lr, betas=(0.5, 0.9))

# Data loading
dataset = datasets.ImageFolder(root='Brain Tumor MRI Dataset/Training', transform=get_transform())
dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True)


# Calculate Gradient Penalty
def compute_gradient_penalty(D, real_samples, fake_samples):
    batch_size, C, H, W = real_samples.size()
    alpha = torch.rand(batch_size, 1, 1, 1, device=device).expand_as(imgs)
    interpolates = alpha * imgs + (1 - alpha) * fake_imgs
    interpolates = interpolates.requires_grad_(True)
    d_interpolates = D(interpolates)
    
    fake = torch.ones(batch_size, device=real_samples.device, requires_grad=False)  # Adjusted shape to match discriminator output
    gradients = torch.autograd.grad(
        outputs=d_interpolates,
        inputs=interpolates,
        grad_outputs=fake,  # Use the adjusted fake tensor
        create_graph=True,
        retain_graph=True,
        only_inputs=True,
    )[0]
    
    gradients = gradients.view(batch_size, -1)
    gradient_penalty = ((gradients.norm(2, dim=1) - 1) ** 2).mean() * lambda_gp
    return gradient_penalty


checkpoint_dir = './training_checkpoints'
checkpoint_path = os.path.join(checkpoint_dir, 'latest_checkpoint.pth')

# Attempt to load the checkpoint if it exists
start_epoch = 0
if os.path.isfile(checkpoint_path):
    start_epoch = load_checkpoint(checkpoint_path, generator, discriminator, g_optimizer, d_optimizer)

# Training loop
for epoch in range(start_epoch, epochs):
    start_time = time.time()  # To track time per epoch
    
    for i, (imgs, _) in enumerate(dataloader):
        imgs = imgs.to(device)

        current_batch_size = imgs.size(0)  # Dynamic batch size

        noise = torch.randn(current_batch_size, noise_vector_size, 1, 1, device=device)
        fake_imgs = generator(noise) 

        # Train Discriminator
        d_optimizer.zero_grad()
        real_validity = discriminator(imgs)
        fake_validity = discriminator(fake_imgs)
        gradient_penalty = compute_gradient_penalty(discriminator, imgs, fake_imgs)
        d_loss = -torch.mean(real_validity) + torch.mean(fake_validity) + gradient_penalty
        d_loss.backward()
        d_optimizer.step()

        # Calculate D(x) and D(G(z)) for printing
        with torch.no_grad():  # We don't need gradients for this part
            # For real images
            D_x = real_validity.mean().item()
            # For fake images
            D_G_z = fake_validity.mean().item()

        # Train Generator less frequently
        if i % n_critic == 0:
            g_optimizer.zero_grad()
            # We need fresh fake images here, using 'noise' instead of 'z'
            gen_imgs = generator(noise)  # Use 'noise' here
            gen_loss = -torch.mean(discriminator(gen_imgs))
            gen_loss.backward()
            g_optimizer.step()

        if i % 40 == 0:
            print(f"[Epoch {epoch}/{epochs}] [Batch {i}/{len(dataloader)}] "
                f"[D loss: {d_loss.item()}] [G loss: {gen_loss.item()}] "
                f"[D(x): {D_x}] [D(G(z)): {D_G_z}]")

    if epoch % 2 == 0:
        checkpoint_path_epoch = os.path.join(checkpoint_dir, f'latest_checkpoint.pth')
        save_checkpoint(epoch, generator, discriminator, g_optimizer, d_optimizer, checkpoint_path_epoch)

    elapsed_time = time.time() - start_time  # Calculate elapsed time
    print(f"Epoch {epoch}/{epochs} completed in {elapsed_time:.2f} seconds.")

    # Save generated images at the end of each epoch
    save_generated_images(gen_imgs.detach(), epoch, directory="generated_images", num_images=10)


# d_loss: The loss of the discriminator should ideally be low but not zero. A low loss indicates that the discriminator 
# is confidently distinguishing between real and fake images. A loss of zero, as seen in epochs 4 and 5, suggests that 
# the discriminator is too confident, which might indicate overfitting or a failure mode.

# g_loss: The loss of the generator should ideally decrease over time. This loss measures how well the generator 
# is fooling the discriminator. However, extremely high values, as seen in your output, suggest that the generator 
# is not performing well.

# D(x): This value should ideally be close to 1, indicating that the discriminator correctly identifies real images as real.
#  Consistently high values close to 1, as seen in your results, indicate that the discriminator is performing its task 
# correctly for real images.

# D(G(z)): This value indicates the discriminator's output for fake images. Early in training, you would expect 
#    this to be closer to 0, as the discriminator can easily tell that the generator's outputs are fake. 
# Over time, as the generator improves, you would expect this value to rise towards 1, indicating that the discriminator 
# is being fooled. A value that remains at 0 indicates the generator is not improving and the discriminator can easily 
# distinguish all fake images.

# Based on the progression you've shown:

# The discriminator is becoming too confident (loss approaching 0), which is a sign that it's potentially overpowering 
# the generator and not providing useful gradients for the generator to learn from.
# The generator loss is very high and increasing, suggesting that it's not successfully fooling the discriminator.