import os


class CommonMds:
	def __init__(self, mds_file, verbose=False):
		self.mds_file = mds_file
		print(self.mds_file)
		assert os.path.isfile(self.mds_file), f"{self.mds_file} does not exist!"
		self.verbose = verbose
		
		self.setup_variables()
		self.read_mds_file()
		
	def setup_variables(self):
		self.no_of_modes = None
		self.no_of_nodes = None
		self.modes = {}
	
	def read_mds_file(self):
		
		with open(self.mds_file) as f:
			if self.verbose:
				print("Reading Data")
			data = f.readlines()
			
		# -------- BLOCK 1 --------
		line = data[0].rstrip().split()
		self.no_of_modes = int(line[0])
		self.no_of_nodes = int(line[1])
		
		if self.verbose:
			print(f"Number of Modes identified as {self.no_of_modes}")
			print(f"Number of Nodes identified as {self.no_of_nodes}")
	
		# -------- BLOCK 2 --------
		for i in range(1, 1 + self.no_of_modes):
			line = data[i].rstrip().split()
			self.modes[int(line[0])] = {"Nat Freq rad_s": float(line[1]), "segments": [],"mode_shape": [], "mode_slope": [], "mode_curvature": []}
			
		# -------- BLOCK 3 --------	
		for line in data[1 + self.no_of_modes:]:
			line = line.rstrip().split()
			self.modes[int(line[0])]["segments"].append(float(line[1]))
			self.modes[int(line[0])]["mode_shape"].append(float(line[2]))
			
				
if __name__ == "__main__":
	
	mds = CommonMds(r"C:\Users\domhnall.morrisey\Documents\Python\Shear7 Testing\Unit Test\common.mds", verbose=True)
	
	import matplotlib.pyplot as plt
	
	nodes = [i for i in range(mds.no_of_nodes)]
	plt.plot(mds.modes[1]["mode_shape"], nodes)
	plt.plot(mds.modes[2]["mode_shape"], nodes)
	#plt.plot(mds.modes[20]["mode_shape"], nodes)
	
	plt.show()