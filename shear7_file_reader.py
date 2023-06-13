import numpy as np
import math
import matplotlib.pyplot as plt
import pandas as pd
from scipy.interpolate import interp1d

class Shear7File:
	def __init__(self, file, version="4.10", verbose=False, print_name=True):
		
		if print_name:
			print(file)
		
		available_versions = ["4.10", "4.6"]
		
		assert version in available_versions, f"Invalide version {version}, the following version are supported {','.join(available_versions)}"
		self.file = file
		self.version = version
		self.verbose = verbose
		
		self.setup_variables()
		self.parse_file()
		self.process_block2()
		self.process_block3()
		self.process_block4()
		self.process_block5()
		
		self.setup_dataframes()
	
	def setup_variables(self):
		self.data = {"headers": []}
		
		#Block 2
		self.total_length = None
		self.total_segments = None
		self.volume_weight_of_fluid = None
		self.kinematic_viscosity_of_fluid = None
		self.structural_damping_coefficient = None
		self.effective_tension_at_origin = None
		self.number_of_section_property_zones = None
		self.section_properties = {}
		
		#Block 3
		self.number_current_points = None
		self.current_profile = []
		self.current_text = ''
		self.max_current = None
		self.min_current = None
		self.mean_current = None
		
		#Block 4
		self.number_of_sn_curves = 0
		self.sn_curves = {}
		self.sn_curves_text = []
		self.global_scf = None
		
		#Block 5
		self.power_value_exponent = None
		self.power_cutoff = None
		self.primary_zone_amplitude_limit = None
		self.riser_diameter = None
		
	def parse_file(self):
		section = "headers"
		
		if self.verbose:
			print("Parsing File")
			
		with open(self.file) as f:
			data = f.readlines()
			
		for line in data:
			if "***" in line:
				section = line.split(".")[0].split("***")[1].strip()
				self.data[section] = []
				
			else:
				self.data[section].append(line)

	def process_block2(self):
		if "BLOCK 2" in self.data:
			if self.verbose:
				print("\nProcessing Block 2")
				
			self.total_length = float(self.data["BLOCK 2"][1].split()[0])
			self.total_segments = int(self.data["BLOCK 2"][2].split()[0])
			self.volume_weight_of_fluid = float(self.data["BLOCK 2"][3].split()[0])
			self.kinematic_viscosity_of_fluid = float(self.data["BLOCK 2"][4].split()[0])
			self.structural_damping_coefficient = float(self.data["BLOCK 2"][5].split()[0])
			self.effective_tension_at_origin = float(self.data["BLOCK 2"][6].split()[0])
			self.number_of_section_property_zones = int(self.data["BLOCK 2"][7].split()[0])

		if self.verbose:
			print(f"Total Length Identified as {self.total_length}")
			print(f"Number of Sectional Property Zones Identified as {self.number_of_section_property_zones}")
			print(f"Structural Damping Coefficient Identified as {self.structural_damping_coefficient}")
			
			# Get Section Properties
			if self.verbose:
				print("\nProcessing Sectional Properties")
			
		count = 0
		for idx in range(8, 8 + (self.number_of_section_property_zones*6), 6):
			section = self.data["BLOCK 2"][idx][50:].strip()
			self.section_properties[count] = {"name": section}

			if self.verbose:
				print(f"\tProcessing Section {count} ({section})")
				
			self.section_properties[count]["start"] = float(self.data["BLOCK 2"][idx].split()[0].replace(",", ""))
			self.section_properties[count]["end"] = float(self.data["BLOCK 2"][idx].split()[1])
			
			self.section_properties[count]["hydro_diameter"] = float(self.data["BLOCK 2"][idx+1].split()[0].replace(",", ""))
			self.section_properties[count]["inertia"] = float(self.data["BLOCK 2"][idx+2].split()[0].replace(",", ""))
			self.section_properties[count]["dry_mass"] = float(self.data["BLOCK 2"][idx+2].split()[1].replace(",", ""))
			self.section_properties[count]["wet_mass"] = float(self.data["BLOCK 2"][idx+2].split()[2].replace(",", ""))
			
			self.section_properties[count]["sn_curve_id"] = int(self.data["BLOCK 2"][idx+3].split()[1])
			
			self.section_properties[count]["bandwidth"] = float(self.data["BLOCK 2"][idx+4].split()[0].replace(",", ""))
			self.section_properties[count]["st_code"] = float(self.data["BLOCK 2"][idx+4].split()[1].replace(",", ""))
			self.section_properties[count]["cl_reduction_factor"] = float(self.data["BLOCK 2"][idx+4].split()[2].replace(",", ""))
			self.section_properties[count]["zoneCLtype"] = int(self.data["BLOCK 2"][idx+4].split()[3].replace(",", ""))
			
			if self.version == "4.10":
				self.section_properties[count]["Ca"] = float(self.data["BLOCK 2"][idx+5].split(",")[0])
				self.section_properties[count]["DampCoeff0"] = float(self.data["BLOCK 2"][idx+5].split(",")[1])
				self.section_properties[count]["DampCoeff1"] = float(self.data["BLOCK 2"][idx+5].split(",")[2])
				self.section_properties[count]["DampCoeff2"] = float(self.data["BLOCK 2"][idx+5].split(",")[3])
				self.section_properties[count]["DampCoeff3"] = float(self.data["BLOCK 2"][idx+5].split(",")[4])
				self.section_properties[count]["DampCoeff4"] = float(self.data["BLOCK 2"][idx+5].split(",")[5].split()[0])
			elif self.version == "4.6":
				self.section_properties[count]["Ca"] = float(self.data["BLOCK 2"][idx+5].split(",")[0])
				self.section_properties[count]["DampCoeff1"] = float(self.data["BLOCK 2"][idx+5].split(",")[1])
				self.section_properties[count]["DampCoeff2"] = float(self.data["BLOCK 2"][idx+5].split(",")[2])
				self.section_properties[count]["DampCoeff3"] = float(self.data["BLOCK 2"][idx+5].split(",")[3].split()[0])			
			count += 1
	
	def process_block3(self):
		if "BLOCK 3" in self.data:
			if self.verbose:
				print("\nProcessing Block 3")
			
			self.number_current_points = int(self.data["BLOCK 3"][0].split()[0].split(",")[0])
			self.current_text = ""
			
			for i in range(1, self.number_current_points + 1):
				depth = float(self.data["BLOCK 3"][i].split(",")[0])
				speed = float(self.data["BLOCK 3"][i].split(",")[1].split()[0])
				self.current_profile.append([depth, speed])
				
				self.current_text = self.current_text + str(depth) + "," + str(speed) + ","
				
			self.current_text = self.current_text[:-1] # remove final comma
			
			if self.number_current_points > 0:
				self.max_current = max([s[1] for s in self.current_profile])
				self.min_current = min([s[1] for s in self.current_profile])
				self.mean_current = round(sum([s[1] for s in self.current_profile]) / len([s[1] for s in self.current_profile]), 4)
			else:
				self.max_current = 0
				self.min_current = 0
				self.mean_current = 0
				
	def process_block4(self):
		if "BLOCK 4" in self.data:
			if self.verbose:
				print("\nProcessing Block 4")
			
			self.number_of_sn_curves = int(self.data["BLOCK 4"][0].split()[0])
			self.global_scf = float(self.data["BLOCK 4"][-2].split()[0].split(",")[0])
			
			line_idx = 1 #first s-n curve line
			for idx in range(1, self.number_of_sn_curves+1):
				
				sn_id = int(self.data["BLOCK 4"][line_idx].split()[0].split(",")[0])
				self.sn_curves[sn_id] = [[], []] #[[stress], [cycles]]
				no_segments = int(self.data["BLOCK 4"][line_idx].split()[1])
				
				for i in range(2, 2 + no_segments + 1):
					line = self.data["BLOCK 4"][line_idx+i].split()
					self.sn_curves[sn_id][0].append(float(line[0].replace(",", "")))
					self.sn_curves[sn_id][1].append(float(line[1].replace(",", "")))
				line_idx += (3 + no_segments)
				
			# Gen text
			for sn_curve_id in self.sn_curves.keys():
				text = str(sn_curve_id)
				for idx, stress in enumerate(self.sn_curves[sn_curve_id][0]):
					text = f"{text},{stress},{self.sn_curves[sn_curve_id][1][idx]}"
				
				self.sn_curves_text.append(text)
	
	def process_block5(self):
		if "BLOCK 5" in self.data:
			if self.verbose:
				print("\nProcessing Block 5")
			
			self.power_cutoff = float(self.data["BLOCK 5"][3].split()[0].replace(",", ""))		
			self.primary_zone_amplitude_limit = float(self.data["BLOCK 5"][3].split()[1].replace(",", ""))		
			self.power_value_exponent = float(self.data["BLOCK 5"][4].split()[0].replace(",", ""))		
			self.riser_diameter = int(self.data["BLOCK 5"][7].split()[0].replace(",", ""))		
		
	def setup_dataframes(self):
		cols = [c for c in list(self.section_properties[0].keys()) if c not in ["start", "end"]]
		self.df_section_properties = pd.DataFrame(columns=["name", "bandwidth"], index=list(self.section_properties.keys()))
		for section in self.section_properties.keys():
			for col in cols:
				self.df_section_properties.at[section, col] = self.section_properties[section][col]
			
		self.df_block2 = pd.DataFrame(columns=["Total Length", "Number Segments", "Weight Fluid", "Structural Damping Coefficient", "Effective Tension Origin"], index=[0])
		self.df_block2.at[0, "Total Length"] = self.total_length
		self.df_block2.at[0, "Number Segments"] = self.total_segments
		self.df_block2.at[0, "Weight Fluid"] = self.volume_weight_of_fluid
		self.df_block2.at[0, "Structural Damping Coefficient"] = self.structural_damping_coefficient
		self.df_block2.at[0, "Effective Tension Origin"] = self.effective_tension_at_origin
		
		self.df_current = pd.DataFrame([[self.current_text, self.max_current, self.min_current, self.mean_current, self.number_current_points]],
						columns=["Current Profile", "Max Current", "Min Current", "Mean Current", "Number Current Points"], index=[0])

		self.df_block4 = pd.DataFrame([[self.number_of_sn_curves, self.global_scf]], columns=["Number S-N Curves", "Global SCF"])
		self.df_block5 = pd.DataFrame([[self.power_cutoff, self.primary_zone_amplitude_limit, self.power_value_exponent, self.riser_diameter]],
							columns=["Power Cutoff", "Primary Zone Amplitude Limit", "Power Value Exponent", "Riser Diameter"])
	
	def generate_segment_data_frame(self):
		x_over_ls = []
		diameters = []
		inertias = []
		strouhals = []
		bandwidths = []
		dry_masses = []
		wet_masses = []
		
		if max([c[0] for c in self.current_profile]) < 1.0: # for current interpolation
				self.current_profile.append([self.current_profile[-1][0]+0.001, 0.0])
				self.current_profile.append([1.0, 0.0])
				
		for section in self.section_properties.keys():
			#start
			x_over_ls.append(self.section_properties[section]["start"])
			diameters.append(self.section_properties[section]["hydro_diameter"])
			inertias.append(self.section_properties[section]["inertia"])
			strouhals.append(self.section_properties[section]["st_code"])
			bandwidths.append(self.section_properties[section]["bandwidth"])
			dry_masses.append(self.section_properties[section]["dry_mass"])
			wet_masses.append(self.section_properties[section]["wet_mass"])
			
			# end
			x_over_ls.append(self.section_properties[section]["end"])
			diameters.append(self.section_properties[section]["hydro_diameter"])
			inertias.append(self.section_properties[section]["inertia"])
			strouhals.append(self.section_properties[section]["st_code"])
			bandwidths.append(self.section_properties[section]["bandwidth"])
			dry_masses.append(self.section_properties[section]["dry_mass"])
			wet_masses.append(self.section_properties[section]["wet_mass"])
			
		# ------ INTERPOLATION FUNCTIONS ------
		f_diameter = interp1d(x_over_ls, diameters)
		f_inertia = interp1d(x_over_ls, inertias)
		f_current = interp1d([p[0] for p in self.current_profile], [p[1] for p in self.current_profile]) # depth current
		f_st = interp1d(x_over_ls, strouhals)
		f_bandwidth = interp1d(x_over_ls, bandwidths)
		f_dry_mass = interp1d(x_over_ls, dry_masses)
		f_wet_mass = interp1d(x_over_ls, wet_masses)
		
		# ------ SETUP DATAFRAME ------
		self.df_segments = pd.DataFrame(columns=["L", "D", "Inertia", "Dry Mass", "Wet Mass", "Current", "CLMax", "St", "Vr", "Vr_crit", "Vr_min", "Vr_max"], index=[i for i in range(self.total_segments+1)])

		# ------ EXCITATION FREQUENCIES
		# 2pi st * V /D
		self.df_segments["Omega"] = np.nan
		
		x_over_l = 0
		for i in range(self.total_segments+1):
			self.df_segments.at[i, "L"] = x_over_l
			self.df_segments.at[i, "D"] = f_diameter(x_over_l)/12
			self.df_segments.at[i, "Inertia"] = f_inertia(x_over_l)
			self.df_segments.at[i, "Dry Mass"] = f_dry_mass(x_over_l)
			self.df_segments.at[i, "Wet Mass"] = f_wet_mass(x_over_l)
			self.df_segments.at[i, "Current"] = f_current(x_over_l)
			self.df_segments.at[i, "CLMax"] = 0.7 #hard coded from CLZone 1
			self.df_segments.at[i, "Rho Fluid"] = 63.981*0.031 #hard coded slugs/ft3
			self.df_segments.at[i, "Omega"] = ((2*math.pi*0.18*f_current(x_over_l))/(f_diameter(x_over_l)/12))*0.1592
			self.df_segments.at[i, "St"] = f_st(x_over_l)
			self.df_segments.at[i, "Vr_crit"] = 1/f_st(x_over_l)
			self.df_segments.at[i, "Bandwidth"] = f_bandwidth(x_over_l)
			self.df_segments.at[i, "Vr_min"] = 1/f_st(x_over_l) - ((f_bandwidth(x_over_l)/2)*1/f_st(x_over_l))
			self.df_segments.at[i, "Vr_max"] = 1/f_st(x_over_l) + ((f_bandwidth(x_over_l)/2)*1/f_st(x_over_l))

			x_over_l += (1/self.total_segments)
			

	def calc_reduced_velocity(self, freq_hz):
		
		for idx, row in self.df_segments.iterrows():
			self.df_segments.at[idx, "Vr"] = row["Current"]/ (freq_hz*(row["D"]))
		
			
if __name__ == "__main__":

	files = [
		r"Z:\114-Projects\OP214967 - Trident Energy - Conductor Fatigue Analysis\02 VIV\02 VIV\750m-10ppg-LB Base Case - VIV (2)\1Yr_Curr.dat",
		r"Z:\114-Projects\OP214967 - Trident Energy - Conductor Fatigue Analysis\02 VIV\02 VIV\750m-10ppg-LB Base Case - VIV (2)\10pc_NE_Curr.dat",
		r"Z:\114-Projects\OP214967 - Trident Energy - Conductor Fatigue Analysis\02 VIV\02 VIV\750m-10ppg-LB Base Case - VIV (2)\20pc_NE_Curr.dat",
		r"Z:\114-Projects\OP214967 - Trident Energy - Conductor Fatigue Analysis\02 VIV\02 VIV\750m-10ppg-LB Base Case - VIV (2)\30pc_NE_Curr.dat",
		r"Z:\114-Projects\OP214967 - Trident Energy - Conductor Fatigue Analysis\02 VIV\02 VIV\750m-10ppg-LB Base Case - VIV (2)\40pc_NE_Curr.dat",
		r"Z:\114-Projects\OP214967 - Trident Energy - Conductor Fatigue Analysis\02 VIV\02 VIV\750m-10ppg-LB Base Case - VIV (2)\50pc_NE_Curr.dat",
		r"Z:\114-Projects\OP214967 - Trident Energy - Conductor Fatigue Analysis\02 VIV\02 VIV\750m-10ppg-LB Base Case - VIV (2)\60pc_NE_Curr.dat",
		r"Z:\114-Projects\OP214967 - Trident Energy - Conductor Fatigue Analysis\02 VIV\02 VIV\750m-10ppg-LB Base Case - VIV (2)\70pc_NE_Curr.dat",
		r"Z:\114-Projects\OP214967 - Trident Energy - Conductor Fatigue Analysis\02 VIV\02 VIV\750m-10ppg-LB Base Case - VIV (2)\80pc_NE_Curr.dat",
		r"Z:\114-Projects\OP214967 - Trident Energy - Conductor Fatigue Analysis\02 VIV\02 VIV\750m-10ppg-LB Base Case - VIV (2)\90pc_NE_Curr.dat",
	]
	
	for file in files:
		file = Shear7File(file)
		
		plt.plot([c[1] for c in file.current_profile], [c[0] for c in file.current_profile], label=file.file.split("\\")[-1])
		
plt.grid()
plt.legend()
plt.show()