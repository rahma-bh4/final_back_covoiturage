from django.db import models
# class User(models.Model):
#     clerk_user_id = models.CharField(max_length=255, unique=True)
#     email = models.EmailField(null=True, blank=True)
#     first_name = models.CharField(max_length=255, null=True, blank=True)
#     created_at = models.DateTimeField(auto_now_add=True)
#     last_name=models.CharField(max_length=255, null=True, blank=True)
#     phone_number = models.CharField(max_length=20, blank=True, null=True)

#     def __str__(self):
#         return self.clerk_user_id
    

    
class Voiture(models.Model):
    id_voiture = models.AutoField(primary_key=True)
    marque = models.CharField(max_length=255)
    #driver_id=models.ForeignKey('Driver', on_delete=models.CASCADE)  # Clé étrangère vers la table Driver
    matricule = models.CharField(max_length=255, unique=True)
    image = models.ImageField(upload_to='voitures/', null=True, blank=True)  
    # L'option pour stocker l'image de la voiture

    def __str__(self):
        return f"{self.marque} - {self.matricule}"

class Trajet(models.Model):
    STATUS_CHOICES = (
       ('active', 'Active'),
        ('ongoing', 'Ongoing'),
        ('completed', 'Completed'),
        ('canceled', 'Canceled'),)
    
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    owner_id=models.ForeignKey('Driver',on_delete=models.CASCADE,blank=True, null=True)  # Clé étrangère vers la table Driver
    phonenumber = models.CharField(max_length=8)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    departure = models.CharField(max_length=255)
    arrival = models.CharField(max_length=255)
    departure_date = models.DateTimeField()  # Date et heure du départ
    arrival_date = models.DateTimeField()  # Date et heure d'arrivée
    nb_places = models.IntegerField()  # Nombre de places disponibles
    voiture = models.ForeignKey(Voiture, on_delete=models.CASCADE)  # Clé étrangère vers la table Voiture
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    def __str__(self):
        return f"{self.id} - {self.name}: {self.departure} -> {self.arrival} ({self.departure_date})"


class Driver(models.Model):
    id = models.AutoField(primary_key=True)
    user_id=models.CharField(max_length=255, unique=True)
    voiture = models.ForeignKey(Voiture, on_delete=models.CASCADE)  # Clé étrangère vers la table Voiture

    

    
# Create your models here.
